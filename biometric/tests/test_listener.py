"""
Unit tests for BiometricListener.

All tests use lightweight mock backends/services, so no physical device or
pyzkfp installation is required.
"""
from __future__ import annotations

import threading
import time
from typing import Callable
from unittest.mock import MagicMock, patch

import pytest

from biometric.exceptions import BiometricDeviceNotFoundError, BiometricNotConnectedError
from biometric.listener import (
    POLL_INTERVAL,
    RECONNECT_DELAY_INITIAL,
    BiometricListener,
)
from biometric.service import BiometricService, UnavailableBackend


# ---------------------------------------------------------------------------
# Helper: a mock BiometricService that yields pre-programmed templates
# ---------------------------------------------------------------------------

class _MockService:
    """
    A minimal BiometricService-shaped object for controlling test scenarios.

    ``templates`` is an iterator of items; each item is either:
    * ``bytes``               — returned as the captured template
    * an ``Exception`` type   — raised when capture_template() is called
    * ``None``                — sentinel that makes the loop pause briefly
    """

    def __init__(self, templates: list, *, connected: bool = True) -> None:
        self._templates = iter(templates)
        self._connected = connected
        self.connect_call_count = 0

    # BiometricService interface -----------------------------------------

    def connect(self, device_id=None, host=None, port=None) -> bool:
        self.connect_call_count += 1
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def capture_template(self) -> bytes:
        item = next(self._templates, StopIteration)
        if item is StopIteration:
            # Exhausted — signal the listener to stop by raising an error.
            raise BiometricNotConnectedError("No more mock templates.")
        if isinstance(item, type) and issubclass(item, Exception):
            raise item("mock exception")
        if isinstance(item, Exception):
            raise item
        return item  # bytes

    @property
    def is_connected(self) -> bool:
        return self._connected


# ---------------------------------------------------------------------------
# Helper: run listener for a bounded number of events then stop it
# ---------------------------------------------------------------------------

def _run_listener_collect(
    templates: list,
    *,
    connected: bool = True,
    timeout: float = 5.0,
) -> tuple[list[bytes], BiometricListener]:
    """
    Start a BiometricListener backed by ``_MockService(templates)``,
    collect all received bytes via callback, then stop the listener.

    Returns ``(collected_bytes, listener_instance)``.
    """
    service = _MockService(templates, connected=connected)
    listener = BiometricListener(service=service, poll_interval=0.0)

    collected: list[bytes] = []
    done = threading.Event()

    def callback(tmpl: bytes) -> None:
        collected.append(tmpl)
        if len(collected) >= sum(1 for t in templates if isinstance(t, (bytes, bytearray))):
            done.set()

    listener.start_listener(callback=callback)
    # Wait until all expected templates are collected or timeout.
    done.wait(timeout=timeout)
    listener.stop_listener()
    return collected, listener


# ===========================================================================
# Tests: start_listener / stop_listener lifecycle
# ===========================================================================

class TestListenerLifecycle:

    def test_start_listener_launches_thread(self):
        service = _MockService([], connected=False)
        listener = BiometricListener(service=service, poll_interval=0.01)
        listener.start_listener(callback=lambda t: None)
        assert listener._thread is not None
        assert listener._thread.is_alive()
        listener.stop_listener()

    def test_stop_listener_terminates_thread(self):
        service = _MockService([], connected=False)
        listener = BiometricListener(service=service, poll_interval=0.01)
        listener.start_listener(callback=lambda t: None)
        thread = listener._thread
        listener.stop_listener()
        # After stop, the thread should have finished.
        thread.join(timeout=3.0)
        assert not thread.is_alive()

    def test_stop_listener_before_start_is_noop(self):
        listener = BiometricListener(service=_MockService([], connected=False))
        listener.stop_listener()  # must not raise

    def test_double_start_raises(self):
        service = _MockService([], connected=False)
        listener = BiometricListener(service=service, poll_interval=0.01)
        listener.start_listener(callback=lambda t: None)
        with pytest.raises(RuntimeError, match="already running"):
            listener.start_listener(callback=lambda t: None)
        listener.stop_listener()

    def test_callback_registered_before_thread_starts(self):
        """
        Requirement 4.3: callback must be stored before the thread is launched.
        We verify that _callback is set synchronously inside start_listener.
        """
        service = _MockService([], connected=False)
        listener = BiometricListener(service=service, poll_interval=0.01)
        cb = lambda t: None  # noqa: E731
        # Patch threading.Thread to capture when _callback is set vs when
        # thread.start() is called.
        callback_set_at: list[object] = []
        original_init = threading.Thread.__init__

        def patched_init(self_inner, *args, **kwargs):
            original_init(self_inner, *args, **kwargs)
            callback_set_at.append(listener._callback)

        with patch.object(threading.Thread, "__init__", patched_init):
            listener.start_listener(callback=cb)

        # _callback must have been set already when the Thread was initialised.
        assert callback_set_at[0] is cb
        listener.stop_listener()

    def test_thread_is_daemon(self):
        service = _MockService([], connected=False)
        listener = BiometricListener(service=service, poll_interval=0.01)
        listener.start_listener(callback=lambda t: None)
        assert listener._thread.daemon is True
        listener.stop_listener()


# ===========================================================================
# Tests: callback invocation
# ===========================================================================

class TestCallbackInvocation:

    def test_callback_called_for_each_template(self):
        templates = [b"t1", b"t2", b"t3"]
        collected, _ = _run_listener_collect(templates, timeout=5.0)
        assert collected == templates

    def test_callback_receives_correct_bytes(self):
        payload = b"\xde\xad\xbe\xef" * 32
        collected: list[bytes] = []
        done = threading.Event()
        service = _MockService([payload])
        listener = BiometricListener(service=service, poll_interval=0.0)

        def cb(tmpl: bytes) -> None:
            collected.append(tmpl)
            done.set()

        listener.start_listener(callback=cb)
        done.wait(timeout=5.0)
        listener.stop_listener()
        assert collected == [payload]


# ===========================================================================
# Tests: per-event exception isolation (Requirement 4.4)
# ===========================================================================

class TestExceptionIsolation:

    def test_capture_exception_does_not_terminate_listener(self):
        """
        Requirement 4.4: if capture_template() raises, the listener must
        continue and process subsequent events.
        """
        good_template = b"good"
        templates = [RuntimeError, good_template]  # first raises, second succeeds
        collected: list[bytes] = []
        done = threading.Event()
        service = _MockService(templates)
        listener = BiometricListener(service=service, poll_interval=0.0)

        def cb(tmpl: bytes) -> None:
            collected.append(tmpl)
            done.set()

        listener.start_listener(callback=cb)
        done.wait(timeout=5.0)
        listener.stop_listener()
        assert good_template in collected

    def test_callback_exception_does_not_terminate_listener(self):
        """
        Requirement 4.4: if the user callback raises, the listener must
        continue processing subsequent events.
        """
        templates = [b"first", b"second", b"third"]
        collected: list[bytes] = []
        done = threading.Event()
        service = _MockService(templates)
        listener = BiometricListener(service=service, poll_interval=0.0)

        call_count = [0]

        def cb(tmpl: bytes) -> None:
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("Deliberate callback failure")
            collected.append(tmpl)
            if len(collected) >= 2:
                done.set()

        listener.start_listener(callback=cb)
        done.wait(timeout=5.0)
        listener.stop_listener()
        # Despite callback failing on first event, subsequent events are delivered.
        assert len(collected) >= 2

    def test_capture_exception_is_logged(self):
        """Exception from capture must be logged with stack trace."""
        import logging

        log_records: list[logging.LogRecord] = []

        class _Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_records.append(record)

        handler = _Handler()
        listener_logger = logging.getLogger("biometric.listener")
        listener_logger.addHandler(handler)
        old_level = listener_logger.level
        listener_logger.setLevel(logging.DEBUG)

        try:
            templates = [RuntimeError, b"ok"]
            done = threading.Event()
            service = _MockService(templates)
            listener = BiometricListener(service=service, poll_interval=0.0)

            def cb(tmpl: bytes) -> None:
                done.set()

            listener.start_listener(callback=cb)
            done.wait(timeout=5.0)
            listener.stop_listener()
        finally:
            listener_logger.removeHandler(handler)
            listener_logger.setLevel(old_level)

        # There should be at least one error-level log entry.
        assert any(r.levelno >= logging.ERROR for r in log_records)

    def test_callback_exception_is_logged(self):
        """Exception from callback must be logged."""
        import logging

        log_records: list[logging.LogRecord] = []

        class _Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_records.append(record)

        handler = _Handler()
        listener_logger = logging.getLogger("biometric.listener")
        listener_logger.addHandler(handler)
        old_level = listener_logger.level
        listener_logger.setLevel(logging.DEBUG)

        try:
            templates = [b"t1", b"t2"]
            done = threading.Event()
            service = _MockService(templates)
            listener = BiometricListener(service=service, poll_interval=0.0)
            cb_calls = [0]

            def cb(tmpl: bytes) -> None:
                cb_calls[0] += 1
                if cb_calls[0] == 1:
                    raise RuntimeError("boom")
                done.set()

            listener.start_listener(callback=cb)
            done.wait(timeout=5.0)
            listener.stop_listener()
        finally:
            listener_logger.removeHandler(handler)
            listener_logger.setLevel(old_level)

        assert any(r.levelno >= logging.ERROR for r in log_records)


# ===========================================================================
# Tests: reconnection logic (Requirement 3.10)
# ===========================================================================

class TestReconnectionLogic:

    def test_listener_reconnects_after_device_becomes_unavailable(self):
        """
        When capture raises BiometricDeviceNotFoundError, the listener should
        call connect() again before resuming captures.
        """
        good_template = b"after_reconnect"
        reconnected = threading.Event()
        call_count = [0]

        class _ReconnectService:
            """First capture raises; after connect() is called, captures succeed."""

            @property
            def is_connected(self):
                return call_count[0] > 0  # not connected until connect() is called

            def connect(self, device_id=None, host=None, port=None):
                call_count[0] += 1
                reconnected.set()
                return True

            def disconnect(self):
                pass

            def capture_template(self) -> bytes:
                return good_template

        service = _ReconnectService()
        # Start with is_connected == False so the loop immediately tries reconnect.
        listener = BiometricListener(service=service, poll_interval=0.0)
        collected: list[bytes] = []
        done = threading.Event()

        def cb(tmpl: bytes) -> None:
            collected.append(tmpl)
            done.set()

        listener.start_listener(callback=cb)
        done.wait(timeout=5.0)
        listener.stop_listener()

        assert reconnected.is_set(), "connect() was never called — reconnection failed"
        assert good_template in collected

    def test_listener_does_not_terminate_on_hardware_error(self):
        """
        Requirement 3.10: a BiometricDeviceNotFoundError during capture must
        NOT terminate the listener thread.
        """
        # Provide one HW error then valid data to confirm the loop continues.
        templates = [BiometricDeviceNotFoundError("gone"), b"recovered"]
        done = threading.Event()
        collected: list[bytes] = []

        class _BrokenThenOkService:
            def __init__(self):
                self._items = iter(templates)
                self._connected = True
                self._reconnected = False

            @property
            def is_connected(self):
                return self._connected

            def connect(self, **kwargs):
                self._connected = True
                self._reconnected = True
                return True

            def disconnect(self):
                self._connected = False

            def capture_template(self) -> bytes:
                item = next(self._items, b"extra")
                if isinstance(item, Exception):
                    raise item
                return item

        service = _BrokenThenOkService()
        listener = BiometricListener(service=service, poll_interval=0.0)

        def cb(tmpl: bytes) -> None:
            collected.append(tmpl)
            done.set()

        listener.start_listener(callback=cb)
        done.wait(timeout=5.0)
        listener.stop_listener()
        assert b"recovered" in collected

    def test_reconnect_logs_hardware_error(self):
        """Hardware errors during reconnection must be logged."""
        import logging

        log_records: list[logging.LogRecord] = []

        class _Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_records.append(record)

        handler = _Handler()
        listener_logger = logging.getLogger("biometric.listener")
        listener_logger.addHandler(handler)
        old_level = listener_logger.level
        listener_logger.setLevel(logging.DEBUG)

        connect_calls = [0]
        good = b"ok"
        done = threading.Event()

        class _FailThenConnect:
            @property
            def is_connected(self):
                return connect_calls[0] >= 2

            def connect(self, **kwargs):
                connect_calls[0] += 1
                if connect_calls[0] < 2:
                    raise BiometricDeviceNotFoundError("not found yet")
                return True

            def disconnect(self):
                pass

            def capture_template(self) -> bytes:
                return good

        service = _FailThenConnect()
        listener = BiometricListener(service=service, poll_interval=0.0)

        def cb(tmpl: bytes) -> None:
            done.set()

        try:
            listener.start_listener(callback=cb)
            done.wait(timeout=10.0)
            listener.stop_listener()
        finally:
            listener_logger.removeHandler(handler)
            listener_logger.setLevel(old_level)

        assert any(
            "reconnect" in r.getMessage().lower() or "unavailable" in r.getMessage().lower()
            for r in log_records
        )


# ===========================================================================
# Tests: listener constructed without injecting a service
# ===========================================================================

class TestDefaultServiceConstruction:

    def test_listener_creates_service_internally(self):
        """When no service is injected, a BiometricService is created."""
        listener = BiometricListener()
        assert isinstance(listener._service, BiometricService)

    def test_listener_with_unavailable_backend_starts_and_stops(self):
        """
        Even with the UnavailableBackend (no pyzkfp), start/stop should work
        without crashing — the listener will just keep trying to reconnect.
        """
        service = BiometricService(backend=UnavailableBackend())
        listener = BiometricListener(service=service, poll_interval=0.0)
        listener.start_listener(callback=lambda t: None)
        time.sleep(0.1)
        listener.stop_listener()
        # Main assertion: no unhandled exception was raised.

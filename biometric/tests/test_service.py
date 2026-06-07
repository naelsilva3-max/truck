"""
Unit tests for BiometricService and related exceptions.

These tests use a small in-process mock backend so they never require the
physical ZKTeco ZK9500 device or the pyzkfp library.
"""
from __future__ import annotations

import pytest

from biometric.exceptions import BiometricDeviceNotFoundError, BiometricNotConnectedError
from biometric.service import BiometricService, UnavailableBackend


# ---------------------------------------------------------------------------
# Minimal mock backend for controlled testing
# ---------------------------------------------------------------------------

class _ConnectedBackend:
    """A backend that pretends to be a connected device."""

    def __init__(self, captured_template: bytes = b"\x01" * 64) -> None:
        self._connected = False
        self._captured = captured_template

    def connect(self, device_id=None, host=None, port=None) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def capture_template(self) -> bytes:
        if not self._connected:
            raise BiometricNotConnectedError()
        return self._captured

    def is_connected(self) -> bool:
        return self._connected


class _FailingConnectBackend:
    """A backend whose connect() always raises BiometricDeviceNotFoundError."""

    def connect(self, device_id=None, host=None, port=None) -> bool:
        raise BiometricDeviceNotFoundError("Device not found (mock).")

    def disconnect(self) -> None:
        pass

    def capture_template(self) -> bytes:  # pragma: no cover
        raise BiometricNotConnectedError()

    def is_connected(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TestBiometricExceptions:
    def test_device_not_found_default_message(self):
        exc = BiometricDeviceNotFoundError()
        assert "not found" in str(exc).lower() or "not accessible" in str(exc).lower()

    def test_device_not_found_custom_message(self):
        exc = BiometricDeviceNotFoundError("custom message")
        assert str(exc) == "custom message"

    def test_not_connected_default_message(self):
        exc = BiometricNotConnectedError()
        assert "connected" in str(exc).lower()

    def test_not_connected_custom_message(self):
        exc = BiometricNotConnectedError("oops")
        assert str(exc) == "oops"


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------

class TestConnect:
    def test_connect_success_returns_true(self):
        svc = BiometricService(backend=_ConnectedBackend())
        assert svc.connect() is True

    def test_connect_raises_when_device_not_found(self):
        svc = BiometricService(backend=_FailingConnectBackend())
        with pytest.raises(BiometricDeviceNotFoundError):
            svc.connect()

    def test_connect_raises_when_pyzkfp_unavailable(self):
        """UnavailableBackend is used when pyzkfp is not installed."""
        svc = BiometricService(backend=UnavailableBackend())
        with pytest.raises(BiometricDeviceNotFoundError):
            svc.connect()


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------

class TestDisconnect:
    def test_disconnect_after_connect_succeeds(self):
        backend = _ConnectedBackend()
        svc = BiometricService(backend=backend)
        svc.connect()
        svc.disconnect()
        assert not backend.is_connected()

    def test_disconnect_without_connect_is_noop(self):
        """disconnect() must be a no-op when not connected (requirement 5.6)."""
        svc = BiometricService(backend=UnavailableBackend())
        svc.disconnect()  # should not raise

    def test_disconnect_twice_is_noop(self):
        backend = _ConnectedBackend()
        svc = BiometricService(backend=backend)
        svc.connect()
        svc.disconnect()
        svc.disconnect()  # second disconnect must not raise


# ---------------------------------------------------------------------------
# capture_template()
# ---------------------------------------------------------------------------

class TestCaptureTemplate:
    def test_capture_returns_bytes_when_connected(self):
        payload = b"\xde\xad\xbe\xef" * 16
        backend = _ConnectedBackend(captured_template=payload)
        svc = BiometricService(backend=backend)
        svc.connect()
        result = svc.capture_template()
        assert isinstance(result, bytes)
        assert result == payload

    def test_capture_raises_when_not_connected(self):
        """capture_template() must raise BiometricNotConnectedError when disconnected."""
        svc = BiometricService(backend=_ConnectedBackend())
        # Never called connect()
        with pytest.raises(BiometricNotConnectedError):
            svc.capture_template()

    def test_capture_raises_after_disconnect(self):
        backend = _ConnectedBackend()
        svc = BiometricService(backend=backend)
        svc.connect()
        svc.disconnect()
        with pytest.raises(BiometricNotConnectedError):
            svc.capture_template()


# ---------------------------------------------------------------------------
# identify()
# ---------------------------------------------------------------------------

class TestIdentify:
    """Tests for the pure-Python exact-bytes fallback (always active when pyzkfp absent)."""

    def _svc(self) -> BiometricService:
        return BiometricService(backend=UnavailableBackend())

    def test_returns_correct_employee_id_on_exact_match(self):
        templates = [(1, b"aaa"), (2, b"bbb"), (3, b"ccc")]
        assert self._svc().identify(b"bbb", templates) == 2

    def test_returns_first_match_when_duplicates(self):
        # Two employees share the same template bytes — return the first one.
        templates = [(1, b"dupe"), (2, b"dupe")]
        assert self._svc().identify(b"dupe", templates) == 1

    def test_returns_none_when_no_match(self):
        templates = [(1, b"aaa"), (2, b"bbb")]
        assert self._svc().identify(b"zzz", templates) is None

    def test_returns_none_for_empty_template_list(self):
        assert self._svc().identify(b"aaa", []) is None

    def test_returns_none_for_single_template_no_match(self):
        templates = [(42, b"template")]
        assert self._svc().identify(b"other", templates) is None

    def test_identifies_first_template(self):
        templates = [(10, b"first"), (20, b"second")]
        assert self._svc().identify(b"first", templates) == 10

    def test_identifies_last_template(self):
        templates = [(10, b"first"), (20, b"second"), (30, b"last")]
        assert self._svc().identify(b"last", templates) == 30


# ---------------------------------------------------------------------------
# is_connected property
# ---------------------------------------------------------------------------

class TestIsConnected:
    def test_false_before_connect(self):
        svc = BiometricService(backend=_ConnectedBackend())
        assert svc.is_connected is False

    def test_true_after_connect(self):
        svc = BiometricService(backend=_ConnectedBackend())
        svc.connect()
        assert svc.is_connected is True

    def test_false_after_disconnect(self):
        svc = BiometricService(backend=_ConnectedBackend())
        svc.connect()
        svc.disconnect()
        assert svc.is_connected is False


# ---------------------------------------------------------------------------
# min_score property
# ---------------------------------------------------------------------------

class TestMinScore:
    def test_default_min_score(self):
        from biometric.service import DEFAULT_MIN_SCORE
        svc = BiometricService(backend=UnavailableBackend())
        assert svc.min_score == DEFAULT_MIN_SCORE

    def test_custom_min_score(self):
        svc = BiometricService(backend=UnavailableBackend(), min_score=75)
        assert svc.min_score == 75

    def test_set_min_score(self):
        svc = BiometricService(backend=UnavailableBackend())
        svc.min_score = 30
        assert svc.min_score == 30

    def test_negative_min_score_raises(self):
        svc = BiometricService(backend=UnavailableBackend())
        with pytest.raises(ValueError):
            svc.min_score = -1

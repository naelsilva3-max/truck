"""
Unit tests for BiometricService and related exceptions.

These tests use a small in-process mock backend so they never require the
physical ZKTeco ZK9500 device or the pyzkfp library.
"""
from __future__ import annotations

import pytest

from biometric.exceptions import BiometricDeviceNotFoundError, BiometricNotConnectedError
from biometric.service import BiometricService, PyzkfpBackend, UnavailableBackend


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


class _SequenceBackend:
    """
    A backend that yields a fixed sequence of captures.

    Each ``capture_template()`` call returns the next item in ``captures``
    (``bytes`` for a finger read, ``None`` for "no finger"); once the sequence
    is exhausted it returns ``None`` (empty sensor).  ``merge_templates`` is
    recorded and returns the configured ``merged`` value.
    """

    def __init__(self, captures: list, merged: bytes = b"MERGED") -> None:
        self._captures = list(captures)
        self._i = 0
        self._connected = False
        self._merged = merged
        self.merge_calls: list[list] = []

    def connect(self, device_id=None, host=None, port=None) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def capture_template(self):
        if not self._connected:
            raise BiometricNotConnectedError()
        if self._i >= len(self._captures):
            return None
        val = self._captures[self._i]
        self._i += 1
        return val

    def merge_templates(self, templates: list[bytes]) -> bytes:
        self.merge_calls.append(list(templates))
        return self._merged

    def is_connected(self) -> bool:
        return self._connected


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

    def test_capture_returns_none_when_no_finger(self):
        """capture_template() returns None (not an error) when the sensor is empty."""
        svc = BiometricService(backend=_SequenceBackend([None]))
        svc.connect()
        assert svc.capture_template() is None


# ---------------------------------------------------------------------------
# capture_blocking()
# ---------------------------------------------------------------------------

class TestCaptureBlocking:
    def test_returns_first_nonempty_read(self):
        svc = BiometricService(backend=_SequenceBackend([None, None, b"fp"]))
        svc.connect()
        assert svc.capture_blocking(timeout=5.0, poll_interval=0.0) == b"fp"

    def test_timeout_raises_when_no_finger(self):
        svc = BiometricService(backend=_SequenceBackend([None, None]))
        svc.connect()
        with pytest.raises(TimeoutError):
            svc.capture_blocking(timeout=0.05, poll_interval=0.01)

    def test_raises_when_not_connected(self):
        svc = BiometricService(backend=_SequenceBackend([b"x"]))
        with pytest.raises(BiometricNotConnectedError):
            svc.capture_blocking()


# ---------------------------------------------------------------------------
# capture_registration()
# ---------------------------------------------------------------------------

class TestCaptureRegistration:
    def test_merges_three_samples(self):
        # s1 <release> s2 <release> s3
        backend = _SequenceBackend([b"s1", None, b"s2", None, b"s3"], merged=b"REG")
        svc = BiometricService(backend=backend)
        svc.connect()
        result = svc.capture_registration(samples=3, timeout=5.0, poll_interval=0.0)
        assert result == b"REG"
        assert backend.merge_calls == [[b"s1", b"s2", b"s3"]]

    def test_single_sample_skips_merge(self):
        backend = _SequenceBackend([b"only"], merged=b"REG")
        svc = BiometricService(backend=backend)
        svc.connect()
        result = svc.capture_registration(samples=1, timeout=5.0, poll_interval=0.0)
        assert result == b"only"
        assert backend.merge_calls == []

    def test_timeout_raises(self):
        backend = _SequenceBackend([])  # never a finger
        svc = BiometricService(backend=backend)
        svc.connect()
        with pytest.raises(TimeoutError):
            svc.capture_registration(samples=3, timeout=0.05, poll_interval=0.01)

    def test_raises_when_not_connected(self):
        svc = BiometricService(backend=_SequenceBackend([b"x"]))
        with pytest.raises(BiometricNotConnectedError):
            svc.capture_registration()


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
# identify() via PyzkfpBackend (DBAdd + DBIdentify 1:N path)
# ---------------------------------------------------------------------------

class _FakeZk:
    """
    Records DB lifecycle calls (DBClear/DBAdd) and returns a pre-programmed
    (finger_id, score) from DBIdentify.
    """

    def __init__(self, identify_result: tuple[int, int] = (0, 0)) -> None:
        self.cleared = False
        self.added: list[tuple[int, bytes]] = []
        self.identify_result = identify_result
        self.identify_calls: list[bytes] = []

    def DBClear(self) -> None:
        self.cleared = True
        self.added.clear()

    def DBAdd(self, fid: int, template: bytes) -> None:
        self.added.append((fid, template))

    def DBIdentify(self, template: bytes):
        self.identify_calls.append(template)
        return self.identify_result


class TestIdentifyWithSdk:
    """
    Coverage for the DBAdd + DBIdentify 1:N flow used against the real
    ZK9500: ``DBMatch`` (1:1 raw comparison) cannot reliably compare a raw
    capture against a ``DBMerge``-produced template on real hardware — every
    enrolled template must instead be loaded into the device's in-memory
    match database via ``DBAdd``, then identified in one ``DBIdentify`` call.
    """

    def test_rebuilds_device_db_and_returns_matched_employee(self):
        backend = PyzkfpBackend()
        fake_zk = _FakeZk(identify_result=(7, 200))
        backend._zk = fake_zk  # simulate a connected device

        svc = BiometricService(backend=backend, min_score=50)
        probe = b"probe-template"
        stored = b"enrolled-merged-template"

        result = svc.identify(probe, [(7, stored)])

        assert result == 7
        assert fake_zk.cleared is True
        assert fake_zk.added == [(7, stored)]
        assert fake_zk.identify_calls == [probe]

    def test_score_below_threshold_returns_none(self):
        backend = PyzkfpBackend()
        backend._zk = _FakeZk(identify_result=(7, 10))  # below min_score
        svc = BiometricService(backend=backend, min_score=50)

        result = svc.identify(b"probe", [(7, b"stored")])
        assert result is None

    def test_no_match_returns_none(self):
        backend = PyzkfpBackend()
        backend._zk = _FakeZk(identify_result=(0, 0))  # finger_id 0 = no match
        svc = BiometricService(backend=backend, min_score=50)

        result = svc.identify(b"probe", [(7, b"stored")])
        assert result is None

    def test_add_failure_for_one_employee_does_not_abort_others(self):
        class _PartiallyFailingZk(_FakeZk):
            def DBAdd(self, fid, template):
                if fid == 1:
                    raise RuntimeError("Failed to add")
                super().DBAdd(fid, template)

        backend = PyzkfpBackend()
        fake_zk = _PartiallyFailingZk(identify_result=(2, 300))
        backend._zk = fake_zk
        svc = BiometricService(backend=backend, min_score=50)

        result = svc.identify(b"probe", [(1, b"broken"), (2, b"good")])
        assert result == 2
        assert fake_zk.added == [(2, b"good")]

    def test_identify_failure_returns_none(self):
        class _FailingIdentifyZk(_FakeZk):
            def DBIdentify(self, template):
                raise RuntimeError("Operation failed")

        backend = PyzkfpBackend()
        backend._zk = _FailingIdentifyZk()
        svc = BiometricService(backend=backend, min_score=50)

        result = svc.identify(b"probe", [(1, b"stored")])
        assert result is None


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

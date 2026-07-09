"""
BiometricService — abstraction layer over the ZKTeco ZK9500 fingerprint reader.

Architecture
------------
The service delegates all hardware I/O to a *backend* object that satisfies the
``BiometricBackend`` protocol.  Two concrete backends are provided:

* ``PyzkfpBackend``  — the real hardware backend, powered by ``pyzkfp``.
* ``UnavailableBackend`` — a stub that raises ``BiometricDeviceNotFoundError``
  for every operation; used when ``pyzkfp`` is not installed.

``BiometricService`` chooses the backend automatically at construction time:
it tries to import ``pyzkfp`` and uses the real backend if the import succeeds;
otherwise it falls back to ``UnavailableBackend``.

The ``identify()`` method always uses pure-Python exact-bytes comparison as a
fallback when ``pyzkfp`` scoring is unavailable, guaranteeing that
``BiometricService.identify()`` works even without the SDK installed (useful
for testing).
"""

from __future__ import annotations

import logging
import time
from typing import Protocol, runtime_checkable

from biometric.exceptions import BiometricDeviceNotFoundError, BiometricNotConnectedError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimum score threshold for pyzkfp 1:N matching
# ---------------------------------------------------------------------------
DEFAULT_MIN_SCORE: int = 50


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class BiometricBackend(Protocol):
    """
    Protocol that every hardware backend must satisfy.
    All method names mirror those of the public ``BiometricService`` API.
    """

    def connect(self, device_id: object | None, host: str | None, port: int | None) -> bool:
        ...  # pragma: no cover

    def disconnect(self) -> None:
        ...  # pragma: no cover

    def capture_template(self) -> bytes | None:
        # Returns the captured template, or None when no finger is on the sensor.
        ...  # pragma: no cover

    def is_connected(self) -> bool:
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Real backend: pyzkfp
# ---------------------------------------------------------------------------

class PyzkfpBackend:
    """
    Backend that talks to the physical ZKTeco ZK9500 via ``pyzkfp``.

    ``pyzkfp`` is imported lazily inside this class so that importing
    ``biometric.service`` never hard-fails on machines where the SDK is absent.
    """

    def __init__(self) -> None:
        self._zk = None  # pyzkfp.ZKFP2 instance
        self._device_index: int | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _import_zkfp(self):
        """Return the pyzkfp module, or raise BiometricDeviceNotFoundError."""
        try:
            import pyzkfp  # noqa: PLC0415
            return pyzkfp
        except ImportError as exc:
            raise BiometricDeviceNotFoundError(
                "pyzkfp library is not installed. "
                "Install it from the ZKTeco SDK or run: pip install pyzkfp"
            ) from exc

    # ------------------------------------------------------------------
    # BiometricBackend interface
    # ------------------------------------------------------------------

    def connect(
        self,
        device_id: int | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> bool:
        """
        Connect to the ZKTeco ZK9500.

        The ZK9500 is a USB desktop scanner driven through the local ZKFinger
        SDK (``pyzkfp``); there is no network/TCP mode.  ``host``/``port`` are
        accepted only to keep the shared backend signature and are rejected
        with a clear error if supplied.

        Parameters
        ----------
        device_id:
            Zero-based USB device index (default 0).
        host, port:
            Not supported for the ZK9500 (USB only).  Passing ``host`` raises
            ``BiometricDeviceNotFoundError``.
        """
        if host is not None:
            raise BiometricDeviceNotFoundError(
                "TCP/IP connection is not supported for the ZKTeco ZK9500. "
                "The reader is a USB device — omit --host/--port."
            )

        pyzkfp = self._import_zkfp()

        try:
            zk = pyzkfp.ZKFP2()
            zk.Init()

            count = zk.GetDeviceCount()
            if count == 0:
                # Nothing to open — release the SDK before bailing out.
                try:
                    zk.Terminate()
                except Exception:  # noqa: BLE001
                    pass
                raise BiometricDeviceNotFoundError(
                    "No ZKTeco ZK9500 device was found.  "
                    "Make sure the reader is connected and the ZKFinger driver is installed."
                )

            idx = int(device_id) if device_id is not None else 0
            # OpenDevice selects the active USB device inside the SDK; it does
            # not return a status code, so success is verified by the device
            # count above and by capture working afterwards.
            zk.OpenDevice(idx)

            self._zk = zk
            self._device_index = idx
            # Note: zk.Light(...) is intentionally not called here — pyzkfp
            # runs it on a background thread that calls SetParameters right
            # after OpenDevice, before the capture stream is running; on the
            # ZK9500 this raises DeviceNotStartedError internally and leaves
            # the device handle unusable for AcquireFingerprint afterwards.
            logger.info("ZKTeco ZK9500 connected successfully (device index %d).", idx)
            return True

        except BiometricDeviceNotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BiometricDeviceNotFoundError(
                f"Unexpected error while connecting to ZKTeco ZK9500: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """
        Release hardware resources.  No-op if already disconnected.

        ``OpenDevice`` claims the USB device at two levels inside pyzkfp; if
        ``CloseDevice`` is skipped and only ``Terminate`` is called, the
        device is left claimed at the driver level and the *next* ``connect()``
        (even from a fresh process) gets a handle that fails with
        ``InvalidHandleError`` on every capture.  Always close before
        terminating.
        """
        if self._zk is None:
            return
        try:
            self._zk.CloseDevice()
        except Exception:  # noqa: BLE001
            logger.warning("Error while closing ZKTeco ZK9500 device.", exc_info=True)
        try:
            self._zk.Terminate()
        except Exception:  # noqa: BLE001
            logger.warning("Error while disconnecting from ZKTeco ZK9500.", exc_info=True)
        finally:
            self._zk = None
            logger.info("ZKTeco ZK9500 disconnected.")

    def capture_template(self) -> bytes | None:
        """
        Read the sensor once (non-blocking).

        ``pyzkfp.AcquireFingerprint()`` returns a ``(template, image)`` tuple
        while a finger is on the sensor, or a falsy value when the sensor is
        empty.  We return only the template bytes, or ``None`` when no finger
        is present, so callers can poll without treating "no finger" as an error.
        """
        if self._zk is None:
            raise BiometricNotConnectedError()

        try:
            capture = self._zk.AcquireFingerprint()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Error capturing fingerprint template: {exc}"
            ) from exc

        if not capture:
            # No finger on the sensor right now.
            return None

        template, _image = capture
        if template is None or len(template) == 0:
            return None
        return bytes(template)

    def merge_templates(self, templates: list[bytes]) -> bytes:
        """
        Merge exactly 3 samples of the same finger into one enrollment
        template via the native ``DBMerge`` call (the ZKTeco-recommended way
        to build a robust template; the native function itself takes exactly
        3 templates — a fixed SDK constraint, not a choice made here).

        This bypasses ``pyzkfp``'s own ``ZKFP2.DBMerge()`` wrapper.  On the
        .NET side, the merged template's real length comes back through a
        ``ref int`` out-parameter (``regTempLen``), but that wrapper discards
        it — it assigns the whole ``(ret, regTempLen)`` tuple pythonnet
        returns to a single ``ret`` variable — so it always reports the full
        padded 2048-byte buffer regardless of the merged template's true
        size. That trailing zero padding is what makes the real device's
        ``DBAdd`` reject the template with ``FailedToAddTemplateError``.  We
        call the low-level binding directly to read the real length and trim
        the buffer to it before returning.
        """
        if self._zk is None:
            raise BiometricNotConnectedError()
        if len(templates) != 3:
            raise ValueError("merge_templates requires exactly 3 samples.")

        from System import Array, Byte  # noqa: PLC0415

        reg_template = Array[Byte](1024 * 2)
        ret, reg_template_len = self._zk.zkfp2.DBMerge(
            self._zk.dbHandle,
            templates[0], templates[1], templates[2],
            reg_template, reg_template.Length,
        )
        if ret != 0:
            raise RuntimeError(f"DBMerge failed (error code {ret}).")
        if reg_template_len <= 0:
            raise RuntimeError("DBMerge returned an empty template.")
        return bytes(reg_template)[:reg_template_len]

    def is_connected(self) -> bool:
        return self._zk is not None

    # ------------------------------------------------------------------
    # pyzkfp 1:N identification (used by BiometricService.identify)
    # ------------------------------------------------------------------
    #
    # ``DBMatch`` (1:1 raw-template comparison) is NOT used here: on the real
    # ZK9500, comparing a freshly captured raw template against a template
    # produced by ``DBMerge`` (i.e. every enrolled template — see
    # ``merge_templates`` above) reliably raises ``OperationFailedError``
    # regardless of argument order.  The SDK's own documented pattern for
    # this exact scenario is to load enrolled templates into the device's
    # in-memory match database via ``DBAdd`` and then run a single 1:N
    # ``DBIdentify`` call against them — this is also what the aqasemi/pyzkfp
    # wrapper special-cases error code -17 ("Operation failed") for,
    # treating it as "no match" instead of raising.

    def clear_enrolled_templates(self) -> None:
        """Clear the device's in-memory match database."""
        if self._zk is None:
            raise BiometricNotConnectedError()
        self._zk.DBClear()

    def add_enrolled_template(self, finger_id: int, template: bytes) -> None:
        """Load one enrolled (merged) template into the device's match database."""
        if self._zk is None:
            raise BiometricNotConnectedError()
        self._zk.DBAdd(finger_id, template)

    def identify_1n(self, template: bytes) -> tuple[int, int]:
        """
        Run a 1:N identification of *template* against every template
        previously loaded via ``add_enrolled_template``.

        Returns ``(finger_id, score)``; ``finger_id`` is 0 when nothing matches.
        """
        if self._zk is None:
            raise BiometricNotConnectedError()
        finger_id, score = self._zk.DBIdentify(template)
        return int(finger_id), int(score)


# ---------------------------------------------------------------------------
# Stub backend: pyzkfp not installed
# ---------------------------------------------------------------------------

class UnavailableBackend:
    """
    Backend used when ``pyzkfp`` is not installed.
    Every hardware operation raises ``BiometricDeviceNotFoundError``.
    """

    _MSG = (
        "The pyzkfp library is not installed.  "
        "Install it from the ZKTeco SDK to enable hardware access."
    )

    def connect(self, device_id=None, host=None, port=None) -> bool:
        raise BiometricDeviceNotFoundError(self._MSG)

    def disconnect(self) -> None:
        # No-op: nothing to disconnect.
        pass

    def capture_template(self) -> bytes | None:
        raise BiometricDeviceNotFoundError(self._MSG)

    def merge_templates(self, templates: list[bytes]) -> bytes:
        raise BiometricDeviceNotFoundError(self._MSG)

    def is_connected(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# BiometricService
# ---------------------------------------------------------------------------

class BiometricService:
    """
    High-level interface for the ZKTeco ZK9500 fingerprint reader.

    Usage
    -----
    ::

        service = BiometricService()
        service.connect()                   # raises BiometricDeviceNotFoundError if unavailable
        template = service.capture_template()
        employee_id = service.identify(template, stored_templates)
        service.disconnect()

    The service can also be constructed with an explicit backend for testing::

        service = BiometricService(backend=MyMockBackend())
    """

    def __init__(
        self,
        backend: BiometricBackend | None = None,
        min_score: int = DEFAULT_MIN_SCORE,
    ) -> None:
        if backend is not None:
            self._backend: BiometricBackend = backend
        else:
            # Auto-detect: use the real SDK if available, otherwise the stub.
            try:
                import pyzkfp  # noqa: F401, PLC0415
                self._backend = PyzkfpBackend()
                logger.debug("BiometricService: using PyzkfpBackend.")
            except ImportError:
                logger.warning(
                    "pyzkfp is not installed.  BiometricService will raise "
                    "BiometricDeviceNotFoundError for all hardware operations."
                )
                self._backend = UnavailableBackend()
            except Exception:
                # pyzkfp is installed but failed to initialize — e.g. pythonnet
                # can't find a .NET/mono runtime, which always happens on a
                # Linux server with no reader attached. Degrade the same way
                # as a missing import instead of letting the view 500.
                logger.warning(
                    "pyzkfp failed to initialize (no compatible .NET/mono runtime on "
                    "this host).  BiometricService will raise BiometricDeviceNotFoundError "
                    "for all hardware operations.",
                    exc_info=True,
                )
                self._backend = UnavailableBackend()

        self._min_score = min_score

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(
        self,
        device_id: int | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> bool:
        """
        Attempt to connect to the ZKTeco ZK9500.

        Parameters
        ----------
        device_id:
            USB device index (0-based).  Ignored when ``host`` is provided.
        host:
            IP address / hostname for TCP/IP mode.
        port:
            TCP port (default 4370) for TCP/IP mode.

        Returns
        -------
        bool
            ``True`` on success.

        Raises
        ------
        BiometricDeviceNotFoundError
            If the device is not found, the SDK is not installed, or the
            connection attempt fails for any reason.
        """
        logger.info(
            "BiometricService.connect called (device_id=%s, host=%s, port=%s).",
            device_id, host, port,
        )
        result = self._backend.connect(device_id=device_id, host=host, port=port)
        logger.info("BiometricService connected successfully.")
        return result

    def disconnect(self) -> None:
        """
        Safely release hardware resources.

        This is a no-op if the device is not currently connected.
        """
        self._backend.disconnect()

    def capture_template(self) -> bytes | None:
        """
        Read the sensor once (non-blocking).

        Returns
        -------
        bytes | None
            The captured template bytes, or ``None`` when no finger is on the
            sensor.  Designed for polling loops (see ``BiometricListener``).

        Raises
        ------
        BiometricNotConnectedError
            If the service is not connected to a device.
        RuntimeError
            If the device errors while reading.
        """
        if not self._backend.is_connected():
            raise BiometricNotConnectedError()
        return self._backend.capture_template()

    def capture_blocking(
        self,
        timeout: float = 15.0,
        poll_interval: float = 0.2,
    ) -> bytes:
        """
        Block until a finger is read or *timeout* seconds elapse.

        Returns the captured template bytes.

        Raises
        ------
        BiometricNotConnectedError
            If the service is not connected.
        TimeoutError
            If no finger is presented within *timeout* seconds.
        """
        if not self._backend.is_connected():
            raise BiometricNotConnectedError()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            template = self._backend.capture_template()
            if template:
                return template
            time.sleep(poll_interval)
        raise TimeoutError("Nenhuma impressão digital foi lida dentro do tempo limite.")

    def _wait_for_release(self, timeout: float, poll_interval: float) -> None:
        """Block until the sensor reports no finger (or *timeout* elapses)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._backend.capture_template():
                return
            time.sleep(poll_interval)

    def capture_registration(
        self,
        samples: int = 3,
        timeout: float = 20.0,
        poll_interval: float = 0.2,
    ) -> bytes:
        """
        Capture *samples* readings of the same finger and merge them into a
        single robust enrollment template (ZKTeco-recommended, via ``DBMerge``).

        The caller is asked, between samples, to lift and re-place the finger;
        this method waits for the finger to be released before each new sample.

        Returns the merged enrollment template bytes.

        Raises
        ------
        BiometricNotConnectedError
            If the service is not connected.
        TimeoutError
            If a sample is not provided within *timeout* seconds.
        RuntimeError
            If merging the samples fails.
        """
        if not self._backend.is_connected():
            raise BiometricNotConnectedError()
        if samples < 1:
            raise ValueError("samples must be >= 1.")

        collected: list[bytes] = []
        for i in range(samples):
            template = self.capture_blocking(timeout=timeout, poll_interval=poll_interval)
            collected.append(template)
            logger.info("Enrollment sample %d/%d captured.", i + 1, samples)
            if i < samples - 1:
                # Require the finger to be lifted before the next sample so the
                # same press is not counted twice.
                self._wait_for_release(timeout=timeout, poll_interval=poll_interval)

        if len(collected) == 1:
            return collected[0]

        merge = getattr(self._backend, "merge_templates", None)
        if merge is None:
            # Backend has no merge support — fall back to the first sample.
            return collected[0]
        return merge(collected)

    def identify(
        self,
        template: bytes,
        templates: list[tuple[int, bytes]],
    ) -> int | None:
        """
        Perform 1:N fingerprint identification.

        The method tries two strategies in order:

        1. **pyzkfp scoring** — if the backend exposes a ``match_score``
           method (i.e. ``PyzkfpBackend`` is in use and connected), it uses the
           SDK's native matching score.  Candidates whose score is below
           ``self._min_score`` are discarded; the best match is returned.

        2. **Pure-Python fallback** — exact byte-for-byte comparison.  Used
           when pyzkfp is unavailable *or* when the backend is not connected.
           Returns the ``employee_id`` of the first template that is
           byte-identical to ``template``, or ``None`` if no exact match is
           found.

        Parameters
        ----------
        template:
            The fingerprint template captured from the device.
        templates:
            A list of ``(employee_id, template_bytes)`` tuples representing
            all enrolled templates to compare against.

        Returns
        -------
        int | None
            The ``employee_id`` of the best-matching employee, or ``None`` if
            no match exceeds the minimum score threshold (or no exact match is
            found in fallback mode).
        """
        if not templates:
            return None

        # Strategy 1: pyzkfp scoring (requires connected PyzkfpBackend)
        if (
            isinstance(self._backend, PyzkfpBackend)
            and self._backend.is_connected()
        ):
            return self._identify_with_sdk(template, templates)

        # Strategy 2: pure-Python exact-bytes fallback
        return self._identify_exact(template, templates)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _identify_with_sdk(
        self,
        template: bytes,
        templates: list[tuple[int, bytes]],
    ) -> int | None:
        """
        Use pyzkfp's native 1:N identification (``DBAdd`` + ``DBIdentify``).

        The device's in-memory match database is rebuilt from *templates* on
        every call.  This is simpler and more robust than comparing bytes in
        Python (``DBMatch`` cannot reliably compare a raw capture against a
        ``DBMerge``-produced template — see ``PyzkfpBackend.identify_1n``),
        and rebuilding is cheap for the employee counts this system targets.
        """
        assert isinstance(self._backend, PyzkfpBackend)

        try:
            self._backend.clear_enrolled_templates()
        except Exception:  # noqa: BLE001
            logger.warning("Failed to clear device match database.", exc_info=True)

        loaded_ids: set[int] = set()
        for employee_id, stored_template in templates:
            try:
                self._backend.add_enrolled_template(employee_id, stored_template)
                loaded_ids.add(employee_id)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Failed to load template for employee %s into device; skipping.",
                    employee_id, exc_info=True,
                )

        if not loaded_ids:
            return None

        try:
            finger_id, score = self._backend.identify_1n(template)
        except Exception:  # noqa: BLE001
            logger.warning("DBIdentify failed.", exc_info=True)
            return None

        if finger_id and finger_id in loaded_ids and score >= self._min_score:
            logger.debug("Identified employee %s with score %d.", finger_id, score)
            return finger_id

        logger.debug(
            "No confident match (finger_id=%s, score=%d, threshold=%d).",
            finger_id, score, self._min_score,
        )
        return None

    @staticmethod
    def _identify_exact(
        template: bytes,
        templates: list[tuple[int, bytes]],
    ) -> int | None:
        """Exact byte-for-byte comparison fallback."""
        for employee_id, stored_template in templates:
            if template == stored_template:
                logger.debug(
                    "Exact-match identification: employee %s.", employee_id
                )
                return employee_id
        return None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """``True`` if the backend currently has an open device connection."""
        return self._backend.is_connected()

    @property
    def min_score(self) -> int:
        """Minimum pyzkfp match score required for a positive identification."""
        return self._min_score

    @min_score.setter
    def min_score(self, value: int) -> None:
        if value < 0:
            raise ValueError("min_score must be a non-negative integer.")
        self._min_score = value

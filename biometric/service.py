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

    def capture_template(self) -> bytes:
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

        Parameters
        ----------
        device_id:
            Zero-based USB device index (default 0 when neither host nor
            device_id is specified).
        host:
            IP address / hostname for TCP/IP connection.
        port:
            TCP port for TCP/IP connection (ignored when ``host`` is None).
        """
        pyzkfp = self._import_zkfp()

        try:
            zk = pyzkfp.ZKFP2()
            zk.Init()

            count = zk.GetDeviceCount()
            if count == 0:
                raise BiometricDeviceNotFoundError(
                    "No ZKTeco ZK9500 device was found.  "
                    "Make sure the reader is connected and powered on."
                )

            if host is not None:
                # TCP/IP connection
                tcp_port = port if port is not None else 4370
                ret = zk.ConnectTCP(host, tcp_port)
            else:
                idx = int(device_id) if device_id is not None else 0
                ret = zk.OpenDevice(idx)

            if ret != 0:
                raise BiometricDeviceNotFoundError(
                    f"Failed to open ZKTeco ZK9500 device (error code {ret})."
                )

            self._zk = zk
            logger.info("ZKTeco ZK9500 connected successfully.")
            return True

        except BiometricDeviceNotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BiometricDeviceNotFoundError(
                f"Unexpected error while connecting to ZKTeco ZK9500: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Release hardware resources.  No-op if already disconnected."""
        if self._zk is None:
            return
        try:
            self._zk.Terminate()
        except Exception:  # noqa: BLE001
            logger.warning("Error while disconnecting from ZKTeco ZK9500.", exc_info=True)
        finally:
            self._zk = None
            logger.info("ZKTeco ZK9500 disconnected.")

    def capture_template(self) -> bytes:
        """Capture a fingerprint template from the connected device."""
        if self._zk is None:
            raise BiometricNotConnectedError()

        try:
            template = self._zk.AcquireFingerprint()
            if template is None or len(template) == 0:
                raise RuntimeError("Device returned an empty template.")
            return bytes(template)
        except (BiometricNotConnectedError, RuntimeError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Error capturing fingerprint template: {exc}"
            ) from exc

    def is_connected(self) -> bool:
        return self._zk is not None

    # ------------------------------------------------------------------
    # pyzkfp scoring (used by BiometricService.identify when available)
    # ------------------------------------------------------------------

    def match_score(self, template1: bytes, template2: bytes) -> int:
        """
        Return the pyzkfp match score between two templates.
        A higher score means a better match.
        """
        if self._zk is None:
            raise BiometricNotConnectedError()
        return int(self._zk.Match(template1, template2))


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

    def capture_template(self) -> bytes:
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

    def capture_template(self) -> bytes:
        """
        Capture a fingerprint template from the connected device.

        Returns
        -------
        bytes
            Raw template bytes returned by the ZK9500.

        Raises
        ------
        BiometricNotConnectedError
            If the service is not connected to a device.
        RuntimeError
            If the device returns an invalid / empty template.
        """
        if not self._backend.is_connected():
            raise BiometricNotConnectedError()
        return self._backend.capture_template()

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
        """Use pyzkfp scoring for 1:N matching."""
        assert isinstance(self._backend, PyzkfpBackend)

        best_score = 0
        best_employee_id: int | None = None

        for employee_id, stored_template in templates:
            try:
                score = self._backend.match_score(template, stored_template)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "match_score failed for employee %s; skipping.", employee_id,
                    exc_info=True,
                )
                continue

            if score > best_score:
                best_score = score
                best_employee_id = employee_id

        if best_score >= self._min_score:
            logger.debug(
                "Identified employee %s with score %d.", best_employee_id, best_score
            )
            return best_employee_id

        logger.debug(
            "Best match score %d is below threshold %d; returning None.",
            best_score, self._min_score,
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

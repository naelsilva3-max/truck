"""
BiometricListener — background thread that continuously monitors the ZKTeco
ZK9500 fingerprint reader and fires a callback for each captured template.

Architecture
------------
``BiometricListener`` owns a ``BiometricService`` instance (or accepts one
injected from the outside for testability) and runs its polling loop inside a
``threading.Thread``, so it never blocks the Django WSGI/ASGI server.

Resilience guarantees
---------------------
* **Per-event exception isolation** (Requirement 4.4): any exception raised
  either by ``BiometricService.capture_template()`` *or* by the user-supplied
  callback is caught, logged with the full stack trace, and then the loop
  continues to the next iteration.
* **Reconnection logic** (Requirement 3.10): when the device becomes
  unavailable (``BiometricDeviceNotFoundError`` or ``BiometricNotConnectedError``),
  the listener logs the hardware error and retries connection with an
  exponential back-off (capped at ``MAX_RECONNECT_DELAY`` seconds) instead of
  terminating.

Usage
-----
::

    service = BiometricService()
    service.connect()

    listener = BiometricListener(service=service)
    listener.start_listener(callback=my_callback)

    # ... later ...
    listener.stop_listener()
    service.disconnect()

Or, to let the listener manage its own ``BiometricService``::

    listener = BiometricListener()
    listener.start_listener(callback=my_callback)
    listener.stop_listener()
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from biometric.exceptions import BiometricDeviceNotFoundError, BiometricNotConnectedError
from biometric.service import BiometricService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reconnection / polling constants
# ---------------------------------------------------------------------------

#: Seconds to sleep between successive capture attempts when the device is
#: available.  Keeps the thread from spinning at 100 % CPU.
POLL_INTERVAL: float = 0.05

#: Initial back-off delay (seconds) when a reconnection attempt fails.
RECONNECT_DELAY_INITIAL: float = 1.0

#: Maximum back-off delay (seconds) between reconnection attempts.
RECONNECT_DELAY_MAX: float = 30.0

#: Multiplicative factor applied to the back-off delay after each failed attempt.
RECONNECT_BACKOFF_FACTOR: float = 2.0


class BiometricListener:
    """
    Polls ``BiometricService.capture_template()`` in a daemon thread and
    invokes a user-supplied callback for every fingerprint template received.

    Parameters
    ----------
    service:
        An optional ``BiometricService`` instance to use.  When *None*, a new
        ``BiometricService()`` is created internally with default settings.
        Injecting a custom service (e.g. one backed by a mock backend) is the
        recommended approach for unit/integration tests.
    device_id:
        Passed to ``BiometricService.connect()`` when the listener needs to
        (re)connect to the device.  Ignored when *host* is provided.
    host:
        IP address / hostname for TCP/IP mode; passed to ``connect()``.
    port:
        TCP port for TCP/IP mode; passed to ``connect()``.
    poll_interval:
        Seconds between capture attempts (default ``POLL_INTERVAL``).
    """

    def __init__(
        self,
        service: BiometricService | None = None,
        device_id: int | None = None,
        host: str | None = None,
        port: int | None = None,
        poll_interval: float = POLL_INTERVAL,
    ) -> None:
        self._service: BiometricService = service if service is not None else BiometricService()
        self._device_id = device_id
        self._host = host
        self._port = port
        self._poll_interval = poll_interval

        self._callback: Callable[[bytes], None] | None = None
        self._stop_event: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        # Debounce: "armed" means we may deliver the next fingerprint.  After
        # an event is delivered we disarm until the sensor reports no finger
        # (i.e. the finger is lifted), so a single press yields a single event.
        self._armed: bool = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_listener(self, callback: Callable[[bytes], None]) -> None:
        """
        Register *callback* and start the background monitoring thread.

        The callback is stored *before* the thread is started, so no event
        can be missed between registration and thread launch (Requirement 4.3).

        Parameters
        ----------
        callback:
            A callable that receives a single ``bytes`` argument — the raw
            fingerprint template captured from the device.  It is invoked from
            the listener thread; implementations must be thread-safe.

        Raises
        ------
        RuntimeError
            If the listener is already running.
        """
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("BiometricListener is already running.")

        # 1. Register the callback BEFORE the thread starts (Requirement 4.3).
        self._callback = callback

        # 2. Clear the stop flag so the loop runs.
        self._stop_event.clear()

        # 3. Start the thread as a daemon so it does not prevent the process
        #    from exiting if stop_listener() is never called.
        self._thread = threading.Thread(
            target=self._listener_loop,
            name="BiometricListenerThread",
            daemon=True,
        )
        self._thread.start()
        logger.info("BiometricListener started (thread id=%d).", self._thread.ident)

    def stop_listener(self) -> None:
        """
        Signal the background thread to stop and wait for it to exit.

        This method blocks until the listener thread has terminated (or until
        a short join timeout expires if the thread is stuck in a back-off
        sleep).  It is safe to call even if the listener was never started.
        """
        if self._thread is None:
            return

        logger.info("BiometricListener stop requested.")
        self._stop_event.set()

        # Give the thread a reasonable window to finish its current iteration.
        self._thread.join(timeout=RECONNECT_DELAY_MAX + 5.0)

        if self._thread.is_alive():
            logger.warning(
                "BiometricListener thread did not stop within the expected "
                "timeout; it will continue as a daemon and exit with the process."
            )

        self._thread = None
        self._callback = None
        logger.info("BiometricListener stopped.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _listener_loop(self) -> None:
        """
        Main polling loop executed inside the background thread.

        The loop alternates between two states:

        * **Connected** — calls ``capture_template()`` repeatedly; any
          exception from capture or from the callback is logged and swallowed
          so that subsequent events are still processed (Requirement 4.4).
        * **Disconnected** — attempts reconnection with exponential back-off;
          hardware errors are logged but do not terminate the loop
          (Requirement 3.10).
        """
        logger.debug("BiometricListener loop starting.")

        # Start armed so the first press is delivered.
        self._armed = True

        while not self._stop_event.is_set():
            if not self._service.is_connected:
                # Device is not connected — try to reconnect.
                self._reconnect_with_backoff()
                # After a (re)connection, re-arm so the next press is delivered.
                self._armed = True
                # If still not connected after backoff exhausted the attempts
                # before stop was set, loop again (which will check stop_event).
                continue

            # Device is connected — attempt a capture.
            try:
                template = self._service.capture_template()
            except (BiometricDeviceNotFoundError, BiometricNotConnectedError) as hw_exc:
                # The device became unavailable mid-session; transition to the
                # reconnection state on the next iteration.
                logger.error(
                    "BiometricListener: device became unavailable during capture. "
                    "Will attempt reconnection. Error: %s",
                    hw_exc,
                    exc_info=True,
                )
                # Mark the service as disconnected by explicitly disconnecting
                # so that the next loop iteration enters reconnect mode.
                try:
                    self._service.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                continue
            except Exception:  # noqa: BLE001
                # Per-event exception isolation (Requirement 4.4): log and continue.
                logger.exception(
                    "BiometricListener: unexpected exception during capture_template(); "
                    "continuing loop."
                )
                time.sleep(self._poll_interval)
                continue

            if not template:
                # No finger on the sensor — the finger was lifted (or never
                # present), so re-arm for the next press.
                self._armed = True
                time.sleep(self._poll_interval)
                continue

            if not self._armed:
                # A finger is still resting on the sensor from the previous
                # event; ignore repeated reads until it is lifted (debounce).
                time.sleep(self._poll_interval)
                continue

            # Deliver exactly one event per press, then disarm until release.
            self._armed = False

            if self._callback is not None:
                try:
                    self._callback(template)
                except Exception:  # noqa: BLE001
                    # Per-event exception isolation (Requirement 4.4): callback
                    # failures must not terminate the listener.
                    logger.exception(
                        "BiometricListener: exception in callback; continuing loop."
                    )

            # Brief sleep to avoid saturating the CPU / USB bus.
            time.sleep(self._poll_interval)

        logger.debug("BiometricListener loop exiting.")

    def _reconnect_with_backoff(self) -> None:
        """
        Attempt to re-establish a connection to the device using exponential
        back-off.  Returns (possibly having given up) when either the
        connection succeeds or the stop flag is set.
        """
        delay = RECONNECT_DELAY_INITIAL

        while not self._stop_event.is_set():
            logger.info(
                "BiometricListener: attempting reconnection to device "
                "(device_id=%s, host=%s, port=%s)...",
                self._device_id, self._host, self._port,
            )
            try:
                self._service.connect(
                    device_id=self._device_id,
                    host=self._host,
                    port=self._port,
                )
                logger.info("BiometricListener: reconnection successful.")
                return  # Connected — return to main loop.
            except (BiometricDeviceNotFoundError, BiometricNotConnectedError) as hw_exc:
                logger.error(
                    "BiometricListener: reconnection failed (%s). "
                    "Retrying in %.1f seconds.",
                    hw_exc,
                    delay,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "BiometricListener: unexpected error during reconnection. "
                    "Retrying in %.1f seconds.",
                    delay,
                )

            # Interruptible sleep: check stop_event every second so that
            # stop_listener() can break out of a long back-off window.
            elapsed = 0.0
            step = 1.0
            while elapsed < delay and not self._stop_event.is_set():
                time.sleep(min(step, delay - elapsed))
                elapsed += step

            # Double the delay for next attempt, capped at the maximum.
            delay = min(delay * RECONNECT_BACKOFF_FACTOR, RECONNECT_DELAY_MAX)

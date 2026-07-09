"""
Shared run-loop for long-lived biometric listener processes.

Django-free by design: imported both by the `start_listener` management
command (runs inside Django) and by the standalone kiosk_agent.py script
(runs on machines with no Django/Postgres installed — see that script's
module docstring). Do not add a Django import here.
"""
from __future__ import annotations

import signal
import time
from typing import Callable


def run_until_shutdown(
    listener,
    service,
    callback: Callable[[bytes], None],
    on_shutdown: Callable[[], None] | None = None,
    poll_interval: float = 1.0,
) -> None:
    """
    Start `listener` with `callback`, then block the calling thread until a
    SIGINT/SIGTERM is received, at which point it runs `on_shutdown()` (if
    given), stops the listener, and disconnects `service`.

    `on_shutdown` runs before the listener is stopped, so it can flip any
    caller-owned background loop's stop flag before teardown proceeds.
    """
    shutdown = {"requested": False}

    def _shutdown(signum, frame):
        if shutdown["requested"]:
            return
        shutdown["requested"] = True
        if on_shutdown is not None:
            on_shutdown()
        listener.stop_listener()
        service.disconnect()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    listener.start_listener(callback=callback)
    while not shutdown["requested"]:
        time.sleep(poll_interval)

"""
kiosk_agent.py — standalone kiosk-side agent for the ZK9500 reader.

Runs on a machine that does NOT have Django/Postgres installed — only
Python + pyzkfp + the vendor ZKFinger driver + requests + python-dotenv.
Talks to the central Django server over HTTPS using a per-device bearer
token (see: python manage.py kiosk_device create --name "...").

This works because biometric/service.py, biometric/listener.py,
biometric/exceptions.py, and biometric/daemon.py have zero Django imports —
copy the `biometric/` package directory alongside this script; no
DJANGO_SETTINGS_MODULE or django.setup() is needed.

Subcommands:
    python kiosk_agent.py enroll --employee-id 42
    python kiosk_agent.py listen

Config (.env file next to this script):
    KIOSK_SERVER_URL=https://your-server.example.com
    KIOSK_DEVICE_TOKEN=<raw token from `manage.py kiosk_device create`>
    KIOSK_DEVICE_ID=0
    KIOSK_TEMPLATE_REFRESH_SECONDS=30
    KIOSK_ENROLL_POLL_SECONDS=5
    KIOSK_HTTP_TIMEOUT=10

Known v1 limitations (see docs/kiosk_deployment.md):
    - A scan that fails to reach the server (network error) is logged and
      dropped — there is no offline queue/retry.
    - A newly enrolled/reactivated/deleted employee's fingerprint may take
      up to KIOSK_TEMPLATE_REFRESH_SECONDS to become (un)recognizable on
      this kiosk — it matches purely against the last locally cached
      template set, independent of the server's current state.
"""
from __future__ import annotations

import argparse
import base64
import logging
import logging.handlers
import os
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import requests

# Under a PyInstaller onefile build, __file__ resolves inside the temporary
# extraction directory (a fresh one per run), not the folder the .exe
# actually lives in — sys.executable is the one that points at the real
# install location in that case. sys.frozen is set by PyInstaller's
# bootloader; plain `python kiosk_agent.py` has neither set.
#
# The installed .exe lives under Program Files, which a standard (non-
# elevated) user — including the Scheduled Task, which intentionally runs
# with the logged-on user's normal token, not admin — cannot write to.
# Mutable runtime files (.env, the log) therefore live in %LOCALAPPDATA%
# for a frozen build; a source checkout keeps the original behavior
# (everything next to the script), since that's what the manual/dev setup
# on this machine already relies on.
if getattr(sys, 'frozen', False):
    _APP_DIR = Path(sys.executable).resolve().parent
    _DATA_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ZK9500Kiosk'
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
else:
    _APP_DIR = Path(__file__).resolve().parent
    _DATA_DIR = _APP_DIR
load_dotenv(dotenv_path=_DATA_DIR / '.env')

from biometric.daemon import run_until_shutdown
from biometric.exceptions import BiometricDeviceNotFoundError, BiometricNotConnectedError
from biometric.listener import BiometricListener
from biometric.service import BiometricService

# A windowed build (no console attached — e.g. run silently by the
# Scheduled Task) has sys.stdout/sys.stderr set to None, so a bare
# StreamHandler would crash on first log call. Always log to a rotating
# file next to the script/exe (or in %LOCALAPPDATA% when frozen — see
# above); add the console handler only when one actually exists, so
# `kiosk_agent.exe enroll` run interactively still prints to the terminal.
_log_handlers: list[logging.Handler] = [
    logging.handlers.RotatingFileHandler(
        _DATA_DIR / 'kiosk_agent.log', maxBytes=5_000_000, backupCount=3, encoding='utf-8',
    ),
]
if sys.stdout is not None:
    _log_handlers.append(logging.StreamHandler())
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=_log_handlers)
logger = logging.getLogger("kiosk_agent")


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Variável de ambiente obrigatória ausente: {name} (configure o .env).")
    return value


SERVER_URL = _required_env("KIOSK_SERVER_URL").rstrip('/')
DEVICE_TOKEN = _required_env("KIOSK_DEVICE_TOKEN")
DEVICE_ID = int(os.environ["KIOSK_DEVICE_ID"]) if os.environ.get("KIOSK_DEVICE_ID") else None
REFRESH_SECONDS = int(os.environ.get("KIOSK_TEMPLATE_REFRESH_SECONDS", "30"))
ENROLL_POLL_SECONDS = float(os.environ.get("KIOSK_ENROLL_POLL_SECONDS", "5"))
HTTP_TIMEOUT = float(os.environ.get("KIOSK_HTTP_TIMEOUT", "10"))


def _headers() -> dict:
    return {"Authorization": f"Bearer {DEVICE_TOKEN}", "Content-Type": "application/json"}


def cmd_enroll(args: argparse.Namespace) -> None:
    service = BiometricService()
    try:
        service.connect(device_id=DEVICE_ID)
    except BiometricDeviceNotFoundError as exc:
        logger.error("Leitor não encontrado: %s", exc)
        sys.exit(1)

    try:
        logger.info("Encoste o dedo 3 vezes, levantando entre cada leitura...")
        template = service.capture_registration(samples=3)
    except TimeoutError as exc:
        logger.error("Tempo de captura esgotado: %s", exc)
        sys.exit(1)
    finally:
        service.disconnect()

    resp = requests.post(
        f"{SERVER_URL}/biometric/api/enroll/",
        headers=_headers(),
        json={
            "employee_id": args.employee_id,
            "template_b64": base64.b64encode(template).decode('ascii'),
        },
        timeout=HTTP_TIMEOUT,
    )
    if resp.ok:
        logger.info("Biometria cadastrada: %s", resp.json())
    else:
        logger.error("Falha ao cadastrar (%s): %s", resp.status_code, resp.text)
        sys.exit(1)


class TemplateCache:
    """
    Periodically refreshed local cache of (employee_id, template_bytes),
    used for local 1:N identification via BiometricService.identify().

    Refresh interval: KIOSK_TEMPLATE_REFRESH_SECONDS (default 30s). A
    just-deactivated (or deleted-biometric) employee may still match
    locally for up to that window, but the server's /api/scan/ endpoint
    independently rejects inactive employees (409), so no attendance is
    ever recorded for a *deactivated* employee regardless of cache
    staleness (defense in depth) — however an *active* employee whose
    fingerprint was merely deleted (still allowed to re-enroll) has no
    such server-side backstop today: a stale local match still records a
    scan for them until the next refresh.
    """

    def __init__(self) -> None:
        self._templates: list[tuple[int, bytes]] = []
        self._lock = threading.Lock()

    def refresh(self) -> None:
        resp = requests.get(
            f"{SERVER_URL}/biometric/api/templates/", headers=_headers(), timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        rows = resp.json()["templates"]
        templates = [
            (row["employee_id"], base64.b64decode(row["template_b64"])) for row in rows
        ]
        with self._lock:
            self._templates = templates
        logger.info("Cache de templates atualizado: %d templates.", len(templates))

    def get(self) -> list[tuple[int, bytes]]:
        with self._lock:
            return list(self._templates)


def _acquire_singleton_lock() -> None:
    """
    Ensure only one `listen` process drives the reader on this machine.

    Windows Task Scheduler (and some shell backgrounding mechanisms) can end
    up with two OS processes for what looks like a single launch; if both
    reach the hardware, they race for the same physical device and produce
    duplicate/garbled attendance reads. A named mutex is visible across the
    whole session regardless of process lineage, so the second process
    always loses the race and exits before touching the reader.
    """
    if sys.platform != "win32":
        return
    import ctypes

    ERROR_ALREADY_EXISTS = 183
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\ZK9500KioskAgentListen")
    if not handle:
        raise ctypes.WinError()
    if ctypes.GetLastError() == ERROR_ALREADY_EXISTS:
        logger.error(
            "Outra instância de 'kiosk_agent.py listen' já está em execução nesta "
            "máquina; encerrando esta para evitar leituras duplicadas do leitor."
        )
        sys.exit(1)
    # Keep a module-level reference so the mutex handle (and thus the lock)
    # stays alive for the lifetime of the process instead of being released
    # as soon as this function returns.
    global _singleton_mutex_handle
    _singleton_mutex_handle = handle


def _check_and_fulfill_enroll_request(listener: BiometricListener, service: BiometricService, on_template) -> None:
    """
    Poll the server for a pending remote-enroll request and, if one exists,
    pause the normal listen loop, capture a fresh fingerprint for it, submit
    it, and resume listening.

    Always resumes the listener in `finally`, even on error, so a single
    failed attempt never leaves the kiosk stuck ignoring finger taps.
    """
    try:
        resp = requests.get(
            f"{SERVER_URL}/biometric/api/enroll-requests/next/", headers=_headers(), timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        logger.warning("Falha ao consultar fila de cadastro remoto; tentando de novo no próximo ciclo.", exc_info=True)
        return

    if not data.get("has_pending"):
        return

    request_id = data["request_id"]
    employee_id = data["employee_id"]
    logger.info(
        "Pedido remoto #%s pendente (funcionário #%s, %s); pausando escuta normal.",
        request_id, employee_id, data.get("employee_name"),
    )
    listener.stop_listener()
    try:
        try:
            if not service.is_connected:
                service.connect(device_id=DEVICE_ID)
            logger.info("Encoste o dedo 3 vezes para o pedido remoto #%s, levantando entre cada leitura...", request_id)
            template = service.capture_registration(samples=3)
        except (BiometricDeviceNotFoundError, BiometricNotConnectedError) as exc:
            logger.error("Leitor indisponível para o pedido remoto #%s: %s", request_id, exc)
            return
        except TimeoutError:
            logger.warning(
                "Tempo esgotado aguardando o dedo (pedido remoto #%s); tentará de novo no próximo ciclo.", request_id,
            )
            return

        try:
            resp = requests.post(
                f"{SERVER_URL}/biometric/api/enroll/",
                headers=_headers(),
                json={
                    "employee_id": employee_id,
                    "template_b64": base64.b64encode(template).decode('ascii'),
                    "enroll_request_id": request_id,
                },
                timeout=HTTP_TIMEOUT,
            )
            if resp.ok:
                logger.info("Pedido remoto #%s atendido: %s", request_id, resp.json())
            else:
                logger.error("Falha ao enviar pedido remoto #%s (%s): %s", request_id, resp.status_code, resp.text)
        except requests.RequestException:
            logger.exception(
                "Erro de rede ao enviar pedido remoto #%s; o pedido segue pendente e será tentado de novo "
                "(vai exigir capturar de novo — sem reenvio do template já lido).", request_id,
            )
    finally:
        try:
            if not service.is_connected:
                service.connect(device_id=DEVICE_ID)
            listener.start_listener(callback=on_template)
        except BiometricDeviceNotFoundError as exc:
            logger.error("Não foi possível retomar a escuta normal após o pedido remoto: %s", exc)


_notify_queue: "queue.Queue[tuple[str, tuple]]" = queue.Queue()
_notify_worker_started = False
_notify_worker_lock = threading.Lock()

# Auto-dismiss delay for the fullscreen notice, in milliseconds.
NOTICE_DISPLAY_MS = 3500


def _format_local_time(iso_timestamp: str | None) -> str:
    """Convert the server's ISO-8601 (UTC) timestamp to a local HH:MM:SS string."""
    if not iso_timestamp:
        return ""
    try:
        return datetime.fromisoformat(iso_timestamp).astimezone().strftime("%H:%M:%S")
    except ValueError:
        return ""


def _show_fullscreen_message(bg: str, title: str, subtitle: str, detail: str = "") -> None:
    import tkinter as tk

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.configure(bg=bg)
    root.config(cursor="none")

    tk.Label(
        root, text=title, font=("Segoe UI", 96, "bold"), fg="white", bg=bg,
    ).pack(expand=True)
    tk.Label(
        root, text=subtitle, font=("Segoe UI", 56, "bold"), fg="white", bg=bg,
    ).pack(expand=True)
    if detail:
        tk.Label(
            root, text=detail, font=("Segoe UI", 40, "bold"), fg="white", bg=bg,
        ).pack(expand=True)

    # Any key/click dismisses early; otherwise it closes itself.
    root.bind("<Button-1>", lambda _e: root.destroy())
    root.bind("<Key>", lambda _e: root.destroy())
    root.after(NOTICE_DISPLAY_MS, root.destroy)
    root.focus_force()
    root.mainloop()


def _notify_worker() -> None:
    try:
        import winsound
    except Exception:
        winsound = None  # noqa: N806

    while True:
        kind, payload = _notify_queue.get()
        try:
            if winsound is not None:
                if kind == "success":
                    winsound.Beep(1500, 200)
                else:
                    winsound.Beep(600, 150)
                    winsound.Beep(600, 150)
        except Exception:
            logger.exception("Falha ao tocar o som de aviso.")
        try:
            if kind == "success":
                employee_name, direction, is_lunch, label, time_label = payload
                is_in = direction == "IN"
                if is_lunch:
                    color = "#b8860b"  # amber — distinct from a full entrada/saída
                else:
                    color = "#1e7e34" if is_in else "#b02a37"  # green (entrada) / red (saída)
                _show_fullscreen_message(
                    color,
                    employee_name,
                    _SCAN_ANNOUNCEMENTS.get(label, "ENTRADA REGISTRADA" if is_in else "SAÍDA REGISTRADA"),
                    detail=f"às {time_label}" if time_label else "",
                )
            else:
                employee_name, retry_after_seconds = payload
                _show_fullscreen_message(
                    "#b8860b",  # amber
                    employee_name,
                    f"REGISTRO NEGADO — aguarde {retry_after_seconds}s",
                )
        except Exception:
            logger.exception("Falha ao mostrar o aviso de ponto (%s).", kind)


def _ensure_notify_worker() -> None:
    global _notify_worker_started
    with _notify_worker_lock:
        if not _notify_worker_started:
            threading.Thread(target=_notify_worker, daemon=True, name="ScanNotify").start()
            _notify_worker_started = True


# Full announcement phrase per server-side `label` (see attendance.service.
# presence_label) — kept here rather than built from `label.upper()` +
# "REGISTRADA/REGISTRADO" client-side to avoid Portuguese gender-agreement
# bugs ("retorno" is masculine, "entrada"/"saída" are feminine).
_SCAN_ANNOUNCEMENTS = {
    "Entrada": "ENTRADA REGISTRADA",
    "Saída": "SAÍDA REGISTRADA",
    "Saída para o Almoço": "SAÍDA PARA O ALMOÇO REGISTRADA",
    "Retorno do Almoço": "RETORNO DO ALMOÇO REGISTRADO",
}


def _notify_scan_success(employee_name: str, direction: str, is_lunch: bool, label: str, time_label: str = "") -> None:
    """
    Give immediate on-screen + audible feedback for a successful scan.

    `kiosk_agent_service.exe` (the Scheduled Task build) runs with no
    console, so without this the person at the reader has no way to know
    the touch actually registered. A single background worker thread owns
    the notice queue and shows one fullscreen notice at a time (auto-
    dismissing — see NOTICE_DISPLAY_MS) so a burst of taps queues up
    instead of fighting over the screen; `on_template`/the listener loop
    itself never blocks on this.
    """
    if sys.platform != "win32":
        return
    _ensure_notify_worker()
    _notify_queue.put(("success", (employee_name, direction, is_lunch, label, time_label)))


def _notify_scan_denied(employee_name: str, retry_after_seconds: int) -> None:
    """Same delivery mechanism as _notify_scan_success, for a rejected (duplicate) scan."""
    if sys.platform != "win32":
        return
    _ensure_notify_worker()
    _notify_queue.put(("denied", (employee_name, retry_after_seconds)))


def cmd_listen(args: argparse.Namespace) -> None:
    _acquire_singleton_lock()
    service = BiometricService()
    try:
        service.connect(device_id=DEVICE_ID)
    except BiometricDeviceNotFoundError as exc:
        logger.error("Leitor não encontrado: %s", exc)
        sys.exit(1)

    cache = TemplateCache()
    try:
        cache.refresh()
    except requests.RequestException:
        logger.exception("Falha na sincronização inicial de templates; iniciando com cache vazio.")

    stop_event = threading.Event()

    def _refresh_loop() -> None:
        while not stop_event.wait(REFRESH_SECONDS):
            try:
                cache.refresh()
            except requests.RequestException:
                logger.exception("Falha na sincronização periódica; mantendo cache anterior.")

    threading.Thread(target=_refresh_loop, daemon=True, name="TemplateRefresh").start()

    def on_template(template: bytes) -> None:
        employee_id = service.identify(template, cache.get())
        if employee_id is None:
            logger.info("Digital não reconhecida; ignorando.")
            return
        try:
            resp = requests.post(
                f"{SERVER_URL}/biometric/api/scan/",
                headers=_headers(),
                json={"employee_id": employee_id},
                timeout=HTTP_TIMEOUT,
            )
            if resp.ok:
                body = resp.json()
                logger.info("Ponto registrado: %s", body)
                _notify_scan_success(
                    body.get("employee_name", f"Funcionário #{employee_id}"),
                    body.get("direction", ""),
                    body.get("is_lunch", False),
                    body.get("label", ""),
                    _format_local_time(body.get("timestamp")),
                )
            elif resp.status_code == 429:
                body = resp.json()
                logger.warning("Registro negado (duplicidade): %s", body)
                _notify_scan_denied(
                    body.get("employee_name", f"Funcionário #{employee_id}"),
                    body.get("retry_after_seconds", 0),
                )
            else:
                # v1 limitation: log + drop. No offline queue/retry — see docs/kiosk_deployment.md.
                logger.error("Falha ao registrar ponto (%s): %s", resp.status_code, resp.text)
        except requests.RequestException:
            logger.exception("Erro de rede ao reportar ponto; evento descartado (sem fila offline no v1).")

    listener = BiometricListener(service=service, device_id=DEVICE_ID)

    def _on_shutdown():
        logger.info("Sinal de encerramento recebido.")
        stop_event.set()

    # Throttled independently of run_until_shutdown's own poll_interval
    # (kept short for responsive Ctrl+C handling) so the enroll queue isn't
    # hit on every tick.
    _next_enroll_check = {"at": 0.0}

    def on_tick() -> None:
        now = time.monotonic()
        if now < _next_enroll_check["at"]:
            return
        _next_enroll_check["at"] = now + ENROLL_POLL_SECONDS
        _check_and_fulfill_enroll_request(listener, service, on_template)

    logger.info("Kiosk agent em execução. Pressione Ctrl+C para parar.")
    run_until_shutdown(listener, service, callback=on_template, on_shutdown=_on_shutdown, on_tick=on_tick)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente de quiosque para o leitor ZKTeco ZK9500.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_enroll = sub.add_parser("enroll", help="Cadastra a digital de um funcionário.")
    p_enroll.add_argument("--employee-id", type=int, required=True)

    sub.add_parser("listen", help="Escuta o leitor continuamente e reporta pontos ao servidor.")

    args = parser.parse_args()
    {"enroll": cmd_enroll, "listen": cmd_listen}[args.command](args)


if __name__ == "__main__":
    main()

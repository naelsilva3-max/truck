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
    KIOSK_TEMPLATE_REFRESH_SECONDS=300
    KIOSK_HTTP_TIMEOUT=10

Known v1 limitations (see docs/kiosk_deployment.md):
    - A scan that fails to reach the server (network error) is logged and
      dropped — there is no offline queue/retry.
    - A newly enrolled/reactivated employee may take up to
      KIOSK_TEMPLATE_REFRESH_SECONDS to become recognizable on this kiosk.
"""
from __future__ import annotations

import argparse
import base64
import logging
import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv
import requests

load_dotenv(dotenv_path=Path(__file__).resolve().parent / '.env')

from biometric.daemon import run_until_shutdown
from biometric.exceptions import BiometricDeviceNotFoundError
from biometric.listener import BiometricListener
from biometric.service import BiometricService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kiosk_agent")


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Variável de ambiente obrigatória ausente: {name} (configure o .env).")
    return value


SERVER_URL = _required_env("KIOSK_SERVER_URL").rstrip('/')
DEVICE_TOKEN = _required_env("KIOSK_DEVICE_TOKEN")
DEVICE_ID = int(os.environ["KIOSK_DEVICE_ID"]) if os.environ.get("KIOSK_DEVICE_ID") else None
REFRESH_SECONDS = int(os.environ.get("KIOSK_TEMPLATE_REFRESH_SECONDS", "300"))
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

    Refresh interval: KIOSK_TEMPLATE_REFRESH_SECONDS (default 300s / 5 min).
    A just-deactivated employee may still match locally for up to that
    window, but the server's /api/scan/ endpoint independently rejects
    inactive employees (409), so no attendance is ever recorded for them
    regardless of cache staleness (defense in depth).
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
                logger.info("Ponto registrado: %s", resp.json())
            else:
                # v1 limitation: log + drop. No offline queue/retry — see docs/kiosk_deployment.md.
                logger.error("Falha ao registrar ponto (%s): %s", resp.status_code, resp.text)
        except requests.RequestException:
            logger.exception("Erro de rede ao reportar ponto; evento descartado (sem fila offline no v1).")

    listener = BiometricListener(service=service, device_id=DEVICE_ID)

    def _on_shutdown():
        logger.info("Sinal de encerramento recebido.")
        stop_event.set()

    logger.info("Kiosk agent em execução. Pressione Ctrl+C para parar.")
    run_until_shutdown(listener, service, callback=on_template, on_shutdown=_on_shutdown)


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

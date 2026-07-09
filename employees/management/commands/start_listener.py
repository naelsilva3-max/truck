"""
Management command: start_listener

Starts the BiometricListener daemon that monitors the ZKTeco ZK9500
fingerprint reader and records employee attendance automatically.

Usage:
    python manage.py start_listener
    python manage.py start_listener --device-id 0
    python manage.py start_listener --host 192.168.1.100 --port 4370

The command runs indefinitely until SIGINT or SIGTERM is received,
then performs a graceful shutdown (stop_listener + disconnect).
"""
import logging

from django.core.management.base import BaseCommand

from attendance.service import AttendanceService
from biometric.daemon import run_until_shutdown
from biometric.exceptions import BiometricDeviceNotFoundError
from biometric.listener import BiometricListener
from biometric.service import BiometricService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Start the biometric listener daemon for automatic attendance recording."

    def add_arguments(self, parser):
        parser.add_argument("--device-id", type=int, default=None, help="USB device index (default 0)")
        parser.add_argument("--host", type=str, default=None, help="TCP/IP host for network-connected reader")
        parser.add_argument("--port", type=int, default=None, help="TCP/IP port (default 4370)")

    def handle(self, *args, **options):
        device_id = options["device_id"]
        host = options["host"]
        port = options["port"]

        logger.info("start_listener: initialising BiometricService...")
        self.stdout.write("Iniciando listener biométrico...")

        service = BiometricService()

        try:
            service.connect(device_id=device_id, host=host, port=port)
            logger.info("start_listener: connected to device.")
            self.stdout.write(self.style.SUCCESS("Leitor biométrico conectado."))
        except BiometricDeviceNotFoundError as exc:
            logger.error("start_listener: device not found — %s", exc)
            self.stderr.write(self.style.ERROR(f"Leitor não encontrado: {exc}"))
            return

        attendance_service = AttendanceService(biometric_service=service)
        listener = BiometricListener(
            service=service,
            device_id=device_id,
            host=host,
            port=port,
        )

        def _on_shutdown():
            logger.info("start_listener: shutdown signal received.")
            self.stdout.write("\nEncerrando listener biométrico...")

        logger.info("start_listener: listener running. Press Ctrl+C to stop.")
        self.stdout.write(self.style.SUCCESS("Listener em execução. Pressione Ctrl+C para parar."))

        run_until_shutdown(
            listener, service,
            callback=attendance_service.process_biometric_event,
            on_shutdown=_on_shutdown,
        )

        logger.info("start_listener: shutdown complete.")
        self.stdout.write(self.style.SUCCESS("Listener encerrado."))

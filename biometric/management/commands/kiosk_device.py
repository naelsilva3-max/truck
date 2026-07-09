"""
Management command: kiosk_device

Issue, list, and revoke KioskDevice bearer tokens for the remote biometric
kiosk agent (kiosk_agent.py, at the repo root).

Usage:
    python manage.py kiosk_device create --name "Recepção - Matriz"
    python manage.py kiosk_device list
    python manage.py kiosk_device revoke --id 3
"""
from django.core.management.base import BaseCommand, CommandError

from biometric.models import KioskDevice


class Command(BaseCommand):
    help = "Manage kiosk device tokens for the remote biometric kiosk API."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='action', required=True)

        p_create = sub.add_parser('create', help='Issue a new device + token.')
        p_create.add_argument('--name', required=True)

        sub.add_parser('list', help='List all devices.')

        p_revoke = sub.add_parser('revoke', help='Revoke a device (soft, reversible).')
        p_revoke.add_argument('--id', type=int, required=True)

    def handle(self, *args, **options):
        action = options['action']

        if action == 'create':
            device, raw_token = KioskDevice.issue(name=options['name'])
            self.stdout.write(self.style.SUCCESS(f"Dispositivo #{device.pk} '{device.name}' criado."))
            self.stdout.write(self.style.WARNING(
                "Copie este token agora — ele NÃO será exibido novamente:"
            ))
            self.stdout.write(raw_token)

        elif action == 'list':
            for d in KioskDevice.objects.all():
                status = 'ativo' if d.is_active else 'REVOGADO'
                self.stdout.write(
                    f"#{d.pk}  {d.name}  [{status}]  prefixo={d.token_prefix}  "
                    f"último_acesso={d.last_seen_at}"
                )

        elif action == 'revoke':
            try:
                device = KioskDevice.objects.get(pk=options['id'])
            except KioskDevice.DoesNotExist:
                raise CommandError(f"Dispositivo #{options['id']} não encontrado.")
            device.is_active = False
            device.save(update_fields=['is_active'])
            self.stdout.write(self.style.SUCCESS(f"Dispositivo #{device.pk} revogado."))

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.tokens import email_verification_token

logger = logging.getLogger('accounts')


def send_verification_email(request, user):
    """Send the email-confirmation link to a newly created (or unverified) user.

    Returns True if the email was sent, False if sending failed (e.g. SMTP
    not configured) — callers should not block user creation on this.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    verify_url = request.build_absolute_uri(
        reverse('accounts:verify_email', kwargs={'uidb64': uid, 'token': token})
    )
    message = render_to_string('accounts/email/verification_email.txt', {
        'user': user,
        'verify_url': verify_url,
    })
    try:
        send_mail(
            subject='Confirme seu email — Controle de Funcionários e Caminhões',
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception('Falha ao enviar email de verificação para %s', user.email)
        return False

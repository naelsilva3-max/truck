from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import SystemLog, UserProfile


def _get_ip(request):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    return ip or request.META.get('REMOTE_ADDR') or None


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    SystemLog(
        user=user,
        username=user.username,
        action=SystemLog.ACTION_LOGIN,
        description='Login realizado',
        ip_address=_get_ip(request),
        path='/accounts/login/',
    ).save()


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user:
        SystemLog(
            user=user,
            username=user.username,
            action=SystemLog.ACTION_LOGOUT,
            description='Logout realizado',
            ip_address=_get_ip(request),
            path='/accounts/logout/',
        ).save()

from accounts.models import SystemLog


def log_action(request, action, description):
    user = request.user if request.user.is_authenticated else None
    username = request.user.username if request.user.is_authenticated else 'anônimo'
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR')
    SystemLog(
        user=user,
        username=username,
        action=action,
        description=description,
        ip_address=ip or None,
        path=request.path,
    ).save()

from accounts.models import SystemLog


def get_client_ip(request):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    return ip or request.META.get('REMOTE_ADDR') or None


def log_action(request, action, description):
    user = request.user if request.user.is_authenticated else None
    username = request.user.username if request.user.is_authenticated else 'anônimo'
    SystemLog(
        user=user,
        username=username,
        action=action,
        description=description,
        ip_address=get_client_ip(request),
        path=request.path,
    ).save()

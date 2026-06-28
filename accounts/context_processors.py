from accounts.mixins import get_role


def user_role(request):
    if not request.user.is_authenticated:
        return {'user_role': 'anonymous', 'can_edit': False, 'is_master': False}
    role = get_role(request.user)
    return {
        'user_role': role,
        'can_edit': role in ('admin', 'master'),
        'is_master': role == 'master',
    }

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect


def get_role(user):
    if user.is_superuser:
        return 'master'
    try:
        return user.profile.role
    except Exception:
        return 'simple'


class RoleRequiredMixin(LoginRequiredMixin):
    allowed_roles = ('simple', 'admin', 'master')

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return response
        role = get_role(request.user)
        if role not in self.allowed_roles:
            messages.error(request, 'Você não tem permissão para acessar esta página.')
            return redirect('employees:list')
        return response


class EditRequiredMixin(RoleRequiredMixin):
    allowed_roles = ('admin', 'master')


class MasterRequiredMixin(RoleRequiredMixin):
    allowed_roles = ('master',)

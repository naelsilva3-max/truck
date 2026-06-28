from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from accounts.logging import log_action
from accounts.mixins import MasterRequiredMixin
from accounts.models import SystemLog, UserProfile
from django.views import View


class UserCreateView(MasterRequiredMixin, View):
    template_name = 'accounts/user_form.html'

    def get(self, request):
        return render(request, self.template_name, {'action': 'Criar'})

    def post(self, request):
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        role = request.POST.get('role', UserProfile.SIMPLE)

        if not username or not password:
            messages.error(request, 'Usuário e senha são obrigatórios.')
            return render(request, self.template_name, {'action': 'Criar'})

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Nome de usuário já existe.')
            return render(request, self.template_name, {'action': 'Criar'})

        if role not in (UserProfile.SIMPLE, UserProfile.ADMIN, UserProfile.MASTER):
            role = UserProfile.SIMPLE

        user = User.objects.create_user(username=username, password=password)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.save()
        log_action(request, SystemLog.ACTION_CREATE, f'Usuário criado: {username} (role={role})')
        messages.success(request, f'Usuário "{username}" criado com sucesso.')
        return redirect('accounts:manage_users')


class UserManageView(MasterRequiredMixin, View):
    template_name = 'accounts/user_manage.html'

    def get(self, request):
        users = User.objects.select_related('profile').order_by('username')
        return render(request, self.template_name, {'users': users})


class UserToggleActiveView(MasterRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target == request.user:
            messages.error(request, 'Você não pode desativar sua própria conta.')
            return redirect('accounts:manage_users')
        target.is_active = not target.is_active
        target.save()
        state = 'reativado' if target.is_active else 'desativado (não conseguirá mais fazer login)'
        log_action(request, SystemLog.ACTION_UPDATE, f'Usuário {target.username} {"ativado" if target.is_active else "desativado"}')
        messages.success(request, f'Usuário "{target.username}" {state}.')
        return redirect('accounts:manage_users')


class UserChangeRoleView(MasterRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        role = request.POST.get('role', UserProfile.SIMPLE)
        if role not in (UserProfile.SIMPLE, UserProfile.ADMIN, UserProfile.MASTER):
            role = UserProfile.SIMPLE
        profile, _ = UserProfile.objects.get_or_create(user=target)
        old_role = profile.role
        profile.role = role
        profile.save()
        log_action(request, SystemLog.ACTION_UPDATE, f'Role de {target.username} alterado de {old_role} para {role}')
        messages.success(request, f'Role de "{target.username}" atualizado para {profile.get_role_display()}.')
        return redirect('accounts:manage_users')


class SystemLogView(MasterRequiredMixin, View):
    template_name = 'accounts/system_log.html'

    def get(self, request):
        qs = SystemLog.objects.select_related('user').exclude(action=SystemLog.ACTION_PAGE_VIEW)

        action = request.GET.get('action')
        user = request.GET.get('user', '').strip()
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')

        if action:
            qs = qs.filter(action=action)
        if user:
            qs = qs.filter(username__icontains=user)
        if start_date:
            qs = qs.filter(timestamp__date__gte=start_date)
        if end_date:
            qs = qs.filter(timestamp__date__lte=end_date)

        return render(request, self.template_name, {'logs': qs})

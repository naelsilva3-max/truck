import re

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from accounts.emails import send_verification_email
from accounts.forms import CPFOrUsernameAuthenticationForm, EmailUpdateForm
from accounts.logging import log_action
from accounts.mixins import MasterRequiredMixin
from accounts.models import SystemLog, UserProfile
from accounts.tokens import email_verification_token
from django.views import View

from employee_truck_control.http import infinite_scroll_json, is_ajax_request
from employee_truck_control.validators import validate_cpf


class CPFLoginView(LoginView):
    template_name = 'registration/login.html'
    authentication_form = CPFOrUsernameAuthenticationForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['login_mode'] = self.request.POST.get('login_mode') or self.request.GET.get('mode', 'cpf')
        return context


class MyAccountView(LoginRequiredMixin, View):
    template_name = 'accounts/my_account.html'

    def get(self, request):
        context = {
            'email_form': EmailUpdateForm(instance=request.user),
            'password_form': PasswordChangeForm(request.user),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        email_form = EmailUpdateForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)

        if 'update_email' in request.POST:
            email_form = EmailUpdateForm(request.POST, instance=request.user)
            if email_form.is_valid():
                email_form.save()
                log_action(request, SystemLog.ACTION_UPDATE, 'Email da própria conta atualizado')
                messages.success(request, 'Email atualizado com sucesso.')
                return redirect('accounts:my_account')
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                log_action(request, SystemLog.ACTION_UPDATE, 'Senha da própria conta atualizada')
                messages.success(request, 'Senha atualizada com sucesso.')
                return redirect('accounts:my_account')

        return render(request, self.template_name, {
            'email_form': email_form,
            'password_form': password_form,
        })


class UserCreateView(MasterRequiredMixin, View):
    template_name = 'accounts/user_form.html'

    def get(self, request):
        return render(request, self.template_name, {'action': 'Criar', 'role_choices': UserProfile.ROLE_CHOICES})

    def post(self, request):
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        email = request.POST.get('email', '').strip()
        cpf = request.POST.get('cpf', '').strip()
        role = request.POST.get('role', UserProfile.SIMPLE)
        ctx = {
            'action': 'Criar',
            'role_choices': UserProfile.ROLE_CHOICES,
            'form_data': {'username': username, 'email': email, 'cpf': cpf, 'role': role},
        }

        if not username or not password or not email or not cpf:
            messages.error(request, 'Usuário, senha, email e CPF são obrigatórios.')
            return render(request, self.template_name, ctx)

        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, 'Email inválido.')
            return render(request, self.template_name, ctx)

        try:
            validate_cpf(cpf)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return render(request, self.template_name, ctx)

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Nome de usuário já existe.')
            return render(request, self.template_name, ctx)

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'Já existe um usuário cadastrado com este email.')
            return render(request, self.template_name, ctx)

        cpf_digits = re.sub(r'\D', '', cpf)
        if UserProfile.objects.filter(cpf=cpf_digits).exists():
            messages.error(request, 'Já existe um usuário cadastrado com este CPF.')
            return render(request, self.template_name, ctx)

        if role not in dict(UserProfile.ROLE_CHOICES):
            role = UserProfile.SIMPLE

        user = User.objects.create_user(username=username, password=password, email=email)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.cpf = cpf_digits
        profile.save()
        log_action(request, SystemLog.ACTION_CREATE, f'Usuário criado: {username} (role={role})')

        if send_verification_email(request, user):
            messages.success(
                request,
                f'Usuário "{username}" criado com sucesso. '
                f'Um email de verificação foi enviado para {email}.',
            )
        else:
            messages.warning(
                request,
                f'Usuário "{username}" criado, mas houve falha ao enviar o email de verificação. '
                'Use a opção "Reenviar verificação" na lista de usuários.',
            )
        return redirect('accounts:manage_users')


class UserManageView(MasterRequiredMixin, View):
    template_name = 'accounts/user_manage.html'
    LIVE_POLL_LIMIT = 50

    def _poll_response(self, request, since):
        """Live-update endpoint: new users created after `since`. Does NOT
        catch existing users' active/role changes (a different mechanism,
        not built yet) — only brand-new rows."""
        since_dt = parse_datetime(since)
        if since_dt is not None and timezone.is_naive(since_dt):
            since_dt = timezone.make_aware(since_dt)

        if since_dt is None:
            new_users = []
        else:
            new_users = list(
                User.objects.select_related('profile')
                .filter(date_joined__gt=since_dt)
                .order_by('-date_joined')[:self.LIVE_POLL_LIMIT]
            )

        html = render_to_string(
            'accounts/_user_rows.html',
            {'users': new_users, 'role_choices': UserProfile.ROLE_CHOICES},
            request=request,
        )
        newest = new_users[0].date_joined.isoformat() if new_users else since

        return JsonResponse({'html': html, 'count': len(new_users), 'newest': newest})

    def get(self, request):
        since = request.GET.get('since')
        if is_ajax_request(request) and since:
            return self._poll_response(request, since)

        users = User.objects.select_related('profile').order_by('username')
        return render(request, self.template_name, {'users': users, 'role_choices': UserProfile.ROLE_CHOICES})


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
        if role not in dict(UserProfile.ROLE_CHOICES):
            role = UserProfile.SIMPLE
        profile, _ = UserProfile.objects.get_or_create(user=target)
        old_role = profile.role
        profile.role = role
        profile.save()
        log_action(request, SystemLog.ACTION_UPDATE, f'Role de {target.username} alterado de {old_role} para {role}')
        messages.success(request, f'Role de "{target.username}" atualizado para {profile.get_role_display()}.')
        return redirect('accounts:manage_users')


class VerifyEmailView(View):
    def get(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and email_verification_token.check_token(user, token):
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.email_verified = True
            profile.save()
            log_action(request, SystemLog.ACTION_UPDATE, f'Email verificado: {user.username}')
            messages.success(request, 'Email verificado com sucesso!')
        else:
            messages.error(request, 'Link de verificação inválido ou expirado.')
        return redirect('login')


class ResendVerificationView(MasterRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        profile, _ = UserProfile.objects.get_or_create(user=target)

        if profile.email_verified:
            messages.info(request, f'O email de "{target.username}" já está verificado.')
        elif not target.email:
            messages.error(request, f'Usuário "{target.username}" não possui email cadastrado.')
        elif send_verification_email(request, target):
            messages.success(request, f'Email de verificação reenviado para {target.email}.')
        else:
            messages.error(request, 'Falha ao enviar o email. Verifique a configuração de SMTP.')
        return redirect('accounts:manage_users')


class SystemLogView(MasterRequiredMixin, View):
    template_name = 'accounts/system_log.html'
    PAGE_SIZE = 50
    LIVE_POLL_LIMIT = 50

    def _filtered_queryset(self, request):
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
        return qs

    def _poll_response(self, request, since):
        """Live-update endpoint: logs created after `since` (ISO timestamp),
        respecting the current filters — SystemLog is append-only/immutable,
        so this only ever needs to look for new rows, never changed ones."""
        since_dt = parse_datetime(since)
        if since_dt is not None and timezone.is_naive(since_dt):
            since_dt = timezone.make_aware(since_dt)

        if since_dt is None:
            new_logs = []
        else:
            new_logs = list(
                self._filtered_queryset(request).filter(timestamp__gt=since_dt).order_by('-timestamp')[:self.LIVE_POLL_LIMIT]
            )

        html = render_to_string('accounts/_log_rows.html', {'logs': new_logs}, request=request)
        newest = new_logs[0].timestamp.isoformat() if new_logs else since

        return JsonResponse({'html': html, 'count': len(new_logs), 'newest': newest})

    def get(self, request):
        from django.core.paginator import Paginator

        since = request.GET.get('since')
        if is_ajax_request(request) and since:
            return self._poll_response(request, since)

        qs = self._filtered_queryset(request)
        paginator = Paginator(qs, self.PAGE_SIZE)
        page_obj = paginator.get_page(request.GET.get('page', 1))

        if is_ajax_request(request):
            return infinite_scroll_json(request, 'accounts/_log_rows.html', {'logs': page_obj}, page_obj)

        return render(request, self.template_name, {'logs': page_obj, 'page_obj': page_obj})

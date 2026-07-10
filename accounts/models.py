from django.contrib.auth.models import User
from django.db import models


from django.core.exceptions import ValidationError

from employee_truck_control.validators import validate_cpf


class UserProfile(models.Model):
    SIMPLE = 'simple'
    ADMIN = 'admin'
    MASTER = 'master'
    ROLE_CHOICES = [(SIMPLE, 'Leitura'), (ADMIN, 'Admin'), (MASTER, 'Master')]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='Usuário',
        help_text='Usuário do sistema associado a este perfil.',
    )
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default=SIMPLE,
        verbose_name='Função',
        help_text='Nível de acesso do usuário: Leitura, Admin ou Master.',
    )
    cpf = models.CharField(
        max_length=11,
        unique=True,
        null=True, blank=True,
        verbose_name='CPF',
        help_text='CPF do usuário, somente números, validado automaticamente.',
    )
    email_verified = models.BooleanField(
        default=False,
        verbose_name='Email verificado',
        help_text='Indica se o usuário confirmou o email recebido no cadastro.',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado em',
        help_text='Data e hora da última atualização deste perfil (inclui alterações de role e do User relacionado, como ativar/desativar).',
    )

    class Meta:
        ordering = ['user__username']
        verbose_name = 'Perfil de Usuário'
        verbose_name_plural = 'Perfis de Usuário'
        indexes = [
            models.Index(fields=['user'], name='idx_userprofile_user'),
            models.Index(fields=['role'], name='idx_userprofile_role'),
        ]

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'

    @property
    def is_simple(self):
        return self.role == self.SIMPLE

    @property
    def is_admin(self):
        return self.role == self.ADMIN

    @property
    def is_master(self):
        return self.role == self.MASTER

    def can_edit(self):
        return self.role in (self.ADMIN, self.MASTER)

    def clean(self):
        if self.role not in dict(self.ROLE_CHOICES):
            raise ValidationError({'role': f'Função inválida: {self.role}.'})
        if self.cpf:
            try:
                validate_cpf(self.cpf)
            except ValidationError as exc:
                raise ValidationError({'cpf': exc.messages})
            conflict = UserProfile.objects.filter(cpf=self.cpf).exclude(pk=self.pk).exists()
            if conflict:
                raise ValidationError({'cpf': 'Já existe um usuário cadastrado com este CPF.'})


class SystemLog(models.Model):
    ACTION_PAGE_VIEW = 'page_view'
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_PDF = 'pdf'
    ACTION_LOGIN = 'login'
    ACTION_LOGOUT = 'logout'

    ACTION_CHOICES = [
        (ACTION_PAGE_VIEW, 'Página Vista'),
        (ACTION_CREATE, 'Criação'),
        (ACTION_UPDATE, 'Atualização'),
        (ACTION_DELETE, 'Exclusão'),
        (ACTION_PDF, 'PDF Impresso'),
        (ACTION_LOGIN, 'Login'),
        (ACTION_LOGOUT, 'Logout'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='system_logs',
        verbose_name='Usuário',
        help_text='Usuário que realizou a ação (pode ser nulo se o usuário foi removido).',
    )
    username = models.CharField(
        max_length=150,
        verbose_name='Nome de Usuário',
        help_text='Nome do usuário no momento da ação (preservado mesmo se o usuário for excluído).',
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        verbose_name='Ação',
        help_text='Tipo de ação realizada (criação, atualização, exclusão, etc.).',
    )
    description = models.TextField(
        verbose_name='Descrição',
        help_text='Descrição detalhada da ação realizada.',
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Data/Hora',
        help_text='Data e hora em que a ação foi registrada.',
    )
    ip_address = models.GenericIPAddressField(
        null=True, blank=True,
        verbose_name='Endereço IP',
        help_text='Endereço IP de onde a ação foi realizada.',
    )
    path = models.CharField(
        max_length=500, blank=True,
        verbose_name='Caminho',
        help_text='URL ou caminho do sistema onde a ação foi executada.',
    )

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Log do Sistema'
        verbose_name_plural = 'Logs do Sistema'
        indexes = [
            models.Index(fields=['-timestamp'], name='idx_systemlog_timestamp'),
            models.Index(fields=['user', 'action'], name='idx_systemlog_user_action'),
            models.Index(fields=['action'], name='idx_systemlog_action'),
        ]

    def __str__(self):
        return f'[{self.timestamp:%d/%m/%Y %H:%M:%S}] {self.username} — {self.get_action_display()}: {self.description}'

    def delete(self, *args, **kwargs):
        raise PermissionError('SystemLog is immutable and cannot be deleted.')

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError('SystemLog is immutable and cannot be modified.')
        super().save(*args, **kwargs)

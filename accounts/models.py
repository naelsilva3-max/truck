from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    SIMPLE = 'simple'
    ADMIN = 'admin'
    MASTER = 'master'
    ROLE_CHOICES = [(SIMPLE, 'Simples'), (ADMIN, 'Admin'), (MASTER, 'Master')]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=SIMPLE)

    class Meta:
        verbose_name = 'Perfil de Usuário'
        verbose_name_plural = 'Perfis de Usuário'

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

    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='system_logs')
    username = models.CharField(max_length=150)  # preserve even if user deleted
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    path = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Log do Sistema'
        verbose_name_plural = 'Logs do Sistema'

    def __str__(self):
        return f'[{self.timestamp:%d/%m/%Y %H:%M:%S}] {self.username} — {self.get_action_display()}: {self.description}'

    def delete(self, *args, **kwargs):
        raise PermissionError('SystemLog is immutable and cannot be deleted.')

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError('SystemLog is immutable and cannot be modified.')
        super().save(*args, **kwargs)

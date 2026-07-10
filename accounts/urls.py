from django.urls import path
from .views import (
    MyAccountView,
    ResendVerificationView,
    SystemLogView,
    UserChangeRoleView,
    UserCreateView,
    UserManageView,
    UserToggleActiveView,
    VerifyEmailView,
)

app_name = 'accounts'

urlpatterns = [
    path('my-account/', MyAccountView.as_view(), name='my_account'),
    path('users/', UserManageView.as_view(), name='manage_users'),
    path('users/new/', UserCreateView.as_view(), name='create_user'),
    path('users/<int:pk>/toggle/', UserToggleActiveView.as_view(), name='toggle_user'),
    path('users/<int:pk>/role/', UserChangeRoleView.as_view(), name='change_role'),
    path('users/<int:pk>/resend-verification/', ResendVerificationView.as_view(), name='resend_verification'),
    path('verify-email/<uidb64>/<token>/', VerifyEmailView.as_view(), name='verify_email'),
    path('logs/', SystemLogView.as_view(), name='system_logs'),
]

from django.urls import path
from .views import UserCreateView, UserManageView, UserToggleActiveView, UserChangeRoleView, SystemLogView

app_name = 'accounts'

urlpatterns = [
    path('users/', UserManageView.as_view(), name='manage_users'),
    path('users/new/', UserCreateView.as_view(), name='create_user'),
    path('users/<int:pk>/toggle/', UserToggleActiveView.as_view(), name='toggle_user'),
    path('users/<int:pk>/role/', UserChangeRoleView.as_view(), name='change_role'),
    path('logs/', SystemLogView.as_view(), name='system_logs'),
]

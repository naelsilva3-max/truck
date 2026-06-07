from django.urls import path
from .views import BiometricSimulatorView

app_name = 'biometric'

urlpatterns = [
    path('simulator/', BiometricSimulatorView.as_view(), name='simulator'),
]

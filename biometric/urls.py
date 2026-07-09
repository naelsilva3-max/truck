from django.urls import path
from .views import BiometricSimulatorView
from .api_views import KioskEnrollView, KioskScanReportView, KioskTemplateSyncView

app_name = 'biometric'

urlpatterns = [
    path('simulator/', BiometricSimulatorView.as_view(), name='simulator'),
    path('api/enroll/', KioskEnrollView.as_view(), name='api_enroll'),
    path('api/templates/', KioskTemplateSyncView.as_view(), name='api_templates'),
    path('api/scan/', KioskScanReportView.as_view(), name='api_scan'),
]

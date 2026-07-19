from django.urls import path
from .views import (
    BiometricSimulatorView,
    KioskInstallerDeleteView,
    KioskInstallerDownloadView,
    KioskInstallerListView,
    KioskTokenDeleteView,
    KioskTokenGenerateView,
)
from .api_views import (
    KioskEnrollRequestNextView,
    KioskEnrollView,
    KioskScanReportView,
    KioskTemplateSyncView,
)

app_name = 'biometric'

urlpatterns = [
    path('simulator/', BiometricSimulatorView.as_view(), name='simulator'),
    path('kiosk-token/', KioskTokenGenerateView.as_view(), name='kiosk_token'),
    path('kiosk-token/<int:pk>/delete/', KioskTokenDeleteView.as_view(), name='kiosk_token_delete'),
    path('kiosk-installer/', KioskInstallerListView.as_view(), name='kiosk_installer'),
    path('kiosk-installer/<int:pk>/download/', KioskInstallerDownloadView.as_view(), name='kiosk_installer_download'),
    path('kiosk-installer/<int:pk>/delete/', KioskInstallerDeleteView.as_view(), name='kiosk_installer_delete'),
    path('api/enroll/', KioskEnrollView.as_view(), name='api_enroll'),
    path('api/enroll-requests/next/', KioskEnrollRequestNextView.as_view(), name='api_enroll_requests_next'),
    path('api/templates/', KioskTemplateSyncView.as_view(), name='api_templates'),
    path('api/scan/', KioskScanReportView.as_view(), name='api_scan'),
]

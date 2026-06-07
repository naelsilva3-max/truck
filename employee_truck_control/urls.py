from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from attendance.views import PresenceHistoryView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("employees/", include("employees.urls")),
    path("employees/", include("attendance.urls")),
    # Global presence history (not employee-scoped)
    path("attendance/presence/", PresenceHistoryView.as_view(), name="presence_history"),
    path("trucks/", include("trucks.urls")),
    path("biometric/", include("biometric.urls")),
    # Redirect root to employee list
    path("", lambda request: redirect("employees:list"), name="root"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

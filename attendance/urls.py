from django.urls import path

from .views import AttendanceListView, PresenceHistoryView

app_name = 'attendance'

urlpatterns = [
    path('<int:pk>/attendance/', AttendanceListView.as_view(), name='list'),
    path('presence/', PresenceHistoryView.as_view(), name='presence_history'),
]

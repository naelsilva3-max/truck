from django.urls import path

from .views import AttendanceListView

app_name = 'attendance'

urlpatterns = [
    path('<int:pk>/attendance/', AttendanceListView.as_view(), name='list'),
]

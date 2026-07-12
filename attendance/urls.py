from django.urls import path

from .views import AttendanceListView, AttendancePendingReviewView

app_name = 'attendance'

urlpatterns = [
    path('<int:pk>/attendance/', AttendanceListView.as_view(), name='list'),
    path('ponto/revisao/', AttendancePendingReviewView.as_view(), name='pending_review'),
    path('ponto/revisao/<int:pk>/', AttendancePendingReviewView.as_view(), name='pending_review_fix'),
]

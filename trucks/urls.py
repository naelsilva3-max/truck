from django.urls import path

from .views import (
    AssignDriverView,
    AssignmentHistoryView,
    GlobalAssignmentHistoryView,
    TruckBrandModelManageView,
    TruckCreateView,
    TruckDetailView,
    TruckListView,
    TruckModelsJsonView,
    TruckReportPDFView,
    TruckUpdateView,
    UnassignDriverView,
)

app_name = 'trucks'

urlpatterns = [
    path('', TruckListView.as_view(), name='list'),
    path('new/', TruckCreateView.as_view(), name='create'),
    path('report/pdf/', TruckReportPDFView.as_view(), name='report_pdf'),
    path('assignments/', GlobalAssignmentHistoryView.as_view(), name='global_assignments'),
    path('brands/', TruckBrandModelManageView.as_view(), name='brands'),
    path('api/models/<int:brand_pk>/', TruckModelsJsonView.as_view(), name='api_models'),
    path('<int:pk>/', TruckDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', TruckUpdateView.as_view(), name='update'),
    path('<int:pk>/assign/', AssignDriverView.as_view(), name='assign'),
    path('<int:pk>/unassign/', UnassignDriverView.as_view(), name='unassign'),
    path('<int:pk>/assignments/', AssignmentHistoryView.as_view(), name='assignments'),
]

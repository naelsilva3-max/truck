"""
URL configuration for the visitors app.

Namespace: visitors
"""
from django.urls import path

from . import views

app_name = "visitors"

urlpatterns = [
    # Visitor CRUD
    path("", views.VisitorListView.as_view(), name="list"),
    path("new/", views.VisitorCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.VisitorUpdateView.as_view(), name="update"),
    # Visit management
    path("visits/", views.VisitListView.as_view(), name="visit_list"),
    path("visits/new/", views.VisitCreateView.as_view(), name="visit_create"),
    path("visits/<int:pk>/", views.VisitDetailView.as_view(), name="visit_detail"),
    path("visits/<int:pk>/depart/", views.VisitDepartView.as_view(), name="visit_depart"),
    path("visits/<int:pk>/badge/", views.VisitBadgePDFView.as_view(), name="visit_badge"),
]
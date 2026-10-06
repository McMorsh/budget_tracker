"""Роутинг раздела «Покупки»."""
from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "contributions/<int:pk>/update/",
        views.contribution_update,
        name="contribution_update",
    ),
    path(
        "contributions/<int:pk>/delete/",
        views.contribution_delete,
        name="contribution_delete",
    ),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/update/", views.purchase_update, name="purchase_update"),
    path("<int:pk>/status/", views.purchase_status, name="purchase_status"),
    path("<int:pk>/delete/", views.purchase_delete, name="purchase_delete"),
]

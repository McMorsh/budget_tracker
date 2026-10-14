"""Роутинг раздела "Траты"."""
from django.urls import path

from . import views

app_name = "expenses"

urlpatterns = [
    path("", views.index, name="index"),
    path("<int:year>/<int:month>/", views.month_detail, name="month"),
    path("<int:pk>/update/", views.transaction_update, name="transaction_update"),
    path("<int:pk>/delete/", views.transaction_delete, name="transaction_delete"),
]

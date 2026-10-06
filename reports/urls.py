"""Роутинг раздела «Отчёты»."""
from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.index, name="index"),
    path("<int:year>/", views.year, name="year"),
    path("<int:year>/<int:month>/", views.month, name="month"),
]

"""Роутинг раздела «Отчёты»."""
from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.index, name="index"),
    path("<int:year>/", views.year, name="year"),
    path("<int:year>/<int:month>/", views.month, name="month"),
    path("<int:year>/<int:month>/pdf/", views.pdf_report, name="pdf"),
    path("<int:year>/pdf/", views.pdf_year_report, name="pdf_year"),
]

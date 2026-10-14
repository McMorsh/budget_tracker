"""Роутинг раздела "Бюджет"."""
from django.urls import path

from . import views

app_name = "budget"

urlpatterns = [
    path("", views.index, name="index"),
    path("<int:year>/<int:month>/", views.month_detail, name="month"),
    path("<int:year>/<int:month>/copy/", views.month_copy, name="month_copy"),
    path("categories/", views.category_list, name="categories"),
    path("categories/create/", views.category_create, name="category_create"),
    path("categories/rename/", views.category_rename, name="category_rename"),
    path("categories/reorder/", views.category_reorder, name="category_reorder"),
    path("categories/<int:pk>/toggle/", views.category_toggle, name="category_toggle"),
]

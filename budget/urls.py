"""Роутинг раздела «Бюджет»."""
from django.urls import path

from . import views

app_name = "budget"

urlpatterns = [
    path("", views.category_list, name="index"),
    path("categories/", views.category_list, name="categories"),
    path("categories/create/", views.category_create, name="category_create"),
    path("categories/rename/", views.category_rename, name="category_rename"),
    path("categories/reorder/", views.category_reorder, name="category_reorder"),
    path("categories/<int:pk>/toggle/", views.category_toggle, name="category_toggle"),
]

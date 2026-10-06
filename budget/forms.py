"""Формы раздела «Бюджет»."""
from django import forms

from .models import Category


class CategoryForm(forms.ModelForm):
    """Валидация названия категории.

    Используется JSON-эндпоинтами `category_create` и `category_rename`.
    Порядок задаётся перетаскиванием в списке (новая категория встаёт
    в конец), активность — архивацией, поэтому в форме только название.
    """

    class Meta:
        model = Category
        fields = ["name"]

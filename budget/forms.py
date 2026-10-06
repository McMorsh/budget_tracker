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


class MonthPlanForm(forms.Form):
    """План месяца: доход, «отложить» и доли категорий.

    Доли категорий — динамические поля `percent_<id>`; пустое значение значит,
    что категория в плане месяца не участвует.
    """

    income = forms.DecimalField(
        label="Доход, ₽",
        min_value=0,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "class": "money-input"}),
    )
    savings_percent = forms.IntegerField(
        label="«Отложить», %",
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(
            attrs={"step": "1", "class": "cell-input", "data-percent": "yes"}
        ),
    )

    def __init__(self, *args, categories=(), **kwargs):
        super().__init__(*args, **kwargs)
        for category in categories:
            self.fields[f"percent_{category.pk}"] = forms.IntegerField(
                required=False,
                min_value=0,
                max_value=100,
                widget=forms.NumberInput(
                    attrs={
                        "step": "1",
                        "class": "cell-input",
                        "data-percent": "yes",
                    }
                ),
            )

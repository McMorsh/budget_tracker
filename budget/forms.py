"""Формы раздела "Бюджет"."""
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Category


class CategoryForm(forms.ModelForm):
    """Валидация названия категории.

    Используется JSON-эндпоинтами `category_create` и `category_rename`.
    Порядок задаётся перетаскиванием в списке (новая категория встаёт
    в конец), активность - архивацией, поэтому в форме только название.

    Владелец обязателен: имена уникальны в пределах владельца, и при
    создании его нужно проставить до проверки уникальности.
    """

    class Meta:
        model = Category
        fields = ["name"]

    def __init__(self, *args, owner: User | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner is not None:
            self.instance.owner = owner

    def clean_name(self) -> str:
        """Проверяет уникальность имени в пределах владельца.

        Django пропускает `UniqueConstraint(owner, name)` в валидации формы,
        пока владелец не входит в её поля, поэтому проверяем сами: иначе
        дубликат падал бы IntegrityError вместо понятной ошибки.
        """
        name = self.cleaned_data["name"]
        same_name = Category.objects.filter(owner=self.instance.owner, name=name)
        if self.instance.pk:
            same_name = same_name.exclude(pk=self.instance.pk)
        if same_name.exists():
            raise ValidationError("Категория с таким названием уже существует.")
        return name


class MonthPlanForm(forms.Form):
    """План месяца: доход, "отложить" и доли категорий.

    Доли категорий - динамические поля `percent_<id>`; пустое значение значит,
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
        label='"Отложить", %',
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

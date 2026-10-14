"""Формы раздела "Покупки"."""
from decimal import Decimal

from django import forms

from budget.utils import MAX_YEAR, MIN_YEAR

from .models import PlannedPurchase, PurchaseContribution


class PlannedPurchaseForm(forms.ModelForm):
    """Цель: что покупаем, стоимость, приоритет и статус.

    Общая форма для добавления (обычный POST с редиректом) и для
    инлайн-правки строки (JSON-эндпоинт `purchase_update`); при инлайн-правке
    статус приходит из строки таблицы без изменений.
    """

    class Meta:
        model = PlannedPurchase
        fields = ["title", "amount", "priority", "status"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "maxlength": "200",
                    "placeholder": "Например, ноутбук",
                    "autofocus": True,
                }
            ),
            "amount": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                    "inputmode": "decimal",
                    "class": "money-input",
                }
            ),
            "priority": forms.NumberInput(
                attrs={"step": "1", "min": "0", "class": "cell-input"}
            ),
        }


class ContributionForm(forms.ModelForm):
    """Взнос в цель: дата, сумма, комментарий."""

    class Meta:
        model = PurchaseContribution
        fields = ["date", "amount", "comment"]
        widgets = {
            "date": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "type": "date",
                    "class": "date-input",
                    "min": f"{MIN_YEAR}-01-01",
                    "max": f"{MAX_YEAR}-12-31",
                },
            ),
            "amount": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0.01",
                    "inputmode": "decimal",
                    "class": "money-input",
                    "autofocus": True,
                }
            ),
            "comment": forms.TextInput(
                attrs={
                    "maxlength": "200",
                    "class": "comment-input",
                    "placeholder": "Комментарий (необязательно)",
                }
            ),
        }

    def clean_amount(self) -> Decimal:
        """Нормализует сумму к двум знакам ("1e3" -> 1000.00)."""
        return self.cleaned_data["amount"].quantize(Decimal("0.01"))

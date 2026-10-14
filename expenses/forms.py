"""Формы раздела "Траты"."""
from decimal import Decimal
from typing import cast

from django import forms
from django.contrib.auth.models import User
from django.db.models import Q

from budget.models import Category
from budget.utils import MAX_YEAR, MIN_YEAR

from .models import Transaction


class CategoryChoiceField(forms.ModelChoiceField):
    """Категория в выпадающем списке: архивные подписаны явно."""

    def label_from_instance(self, obj) -> str:
        return f"{obj.name} (в архиве)" if not obj.is_active else obj.name


class TransactionForm(forms.ModelForm):
    """Трата: дата, категория, сумма, комментарий.

    Общая форма для быстрого ввода (обычный POST с редиректом) и для
    инлайн-правки строки (JSON-эндпоинт `transaction_update`).
    """

    category = CategoryChoiceField(
        label="Категория",
        queryset=Category.objects.none(),  # переопределяется в __init__
        empty_label="Выберите категорию",
    )

    class Meta:
        model = Transaction
        fields = ["date", "category", "amount", "comment"]
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

    def __init__(self, *args, owner: User, **kwargs):
        super().__init__(*args, **kwargs)
        # Новым тратам владелец ставится здесь: форма - единственная точка
        # создания, а поле owner в форме не показывается.
        if not self.instance.pk:
            self.instance.owner = owner
        # Новые траты - только по активным категориям владельца. При правке
        # уже сохранённой траты её категория остаётся доступной, даже если
        # она в архиве: иначе строку не сохранить.
        categories = Category.objects.filter(owner=owner, is_active=True)
        if self.instance.pk:
            current = self.instance.category
            if not current.is_active:
                categories = Category.objects.filter(owner=owner).filter(
                    Q(is_active=True) | Q(pk=current.pk)
                )
        field = cast(CategoryChoiceField, self.fields["category"])
        field.queryset = categories

    def clean_amount(self) -> Decimal:
        """Нормализует сумму к двум знакам ("1e3" → 1000.00)."""
        return self.cleaned_data["amount"].quantize(Decimal("0.01"))

"""Модели трат.

Месяц траты не хранится: он определяется по дате (`timezone.localdate()`
для значения по умолчанию). Категория защищена от удаления (PROTECT) -
категории архивируются, история трат сохраняется.
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from budget.models import Category
from budget.utils import MAX_YEAR, MIN_YEAR


class Transaction(models.Model):
    """Трата: дата, категория, сумма, комментарий."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="владелец",
    )
    # Границы те же, что у навигации по месяцам (`budget.utils`): дата вне
    # диапазона увела бы после сохранения на несуществующий экран.
    date = models.DateField(
        "дата",
        default=timezone.localdate,
        validators=[
            MinValueValidator(date(MIN_YEAR, 1, 1)),
            MaxValueValidator(date(MAX_YEAR, 12, 31)),
        ],
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name="категория",
    )
    amount = models.DecimalField(
        "сумма, ₽",
        max_digits=12,
        decimal_places=2,
        # Валидатор дублирует CheckConstraint ниже, но срабатывает в формах
        # (включая инлайн-правку и админку), а не только на уровне базы.
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    comment = models.CharField("комментарий", max_length=200, blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "трата"
        verbose_name_plural = "траты"
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["date"], name="transaction_date_idx"),
            models.Index(fields=["category", "date"], name="transaction_cat_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="transaction_amount_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.date:%d.%m.%Y} - {self.category}: {self.amount} ₽"

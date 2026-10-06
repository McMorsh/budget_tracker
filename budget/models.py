"""Модели бюджета: категории, месяцы и распределение дохода.

Деньги — только DecimalField, валюта одна (₽).
План распределения хранится в процентах от дохода (включая «отложить»);
рубли — производные: доход месяца × доля, округление до копеек.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils.formats import date_format

from .utils import MAX_YEAR, MIN_YEAR


def money(value: Decimal) -> Decimal:
    """Округляет сумму до копеек (половина — вверх)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def planned_amount(income: Decimal, percent: int) -> Decimal:
    """Плановая сумма: доход × доля, округление до копеек (ROUND_HALF_UP)."""
    return money(income * percent / 100)


class Category(models.Model):
    """Категория трат (архивируется, а не удаляется)."""

    name = models.CharField("название", max_length=100, unique=True)
    position = models.PositiveSmallIntegerField("порядок", default=0)
    is_active = models.BooleanField("активна", default=True)

    class Meta:
        verbose_name = "категория"
        verbose_name_plural = "категории"
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name


class BudgetMonth(models.Model):
    """Бюджетный месяц: доход и план «отложить»."""

    year = models.PositiveSmallIntegerField(
        "год",
        validators=[MinValueValidator(MIN_YEAR), MaxValueValidator(MAX_YEAR)],
    )
    month = models.PositiveSmallIntegerField(
        "месяц",
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    income = models.DecimalField(
        "доход, ₽",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
    )
    savings_percent = models.PositiveSmallIntegerField(
        "«отложить», % от дохода",
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    class Meta:
        verbose_name = "бюджетный месяц"
        verbose_name_plural = "бюджетные месяцы"
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["year", "month"],
                name="unique_budget_month",
            ),
            models.CheckConstraint(
                condition=Q(income__gte=0),
                name="budget_income_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(savings_percent__gte=0) & Q(savings_percent__lte=100),
                name="budget_savings_percent_range",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def title(self) -> str:
        """Название месяца по-русски, например «Октябрь 2026»."""
        return date_format(date(self.year, self.month, 1), "F Y")

    @property
    def savings_amount(self) -> Decimal:
        """План «отложить» в рублях."""
        return planned_amount(self.income, self.savings_percent)

    @property
    def allocations_total_percent(self) -> int:
        """Σ долей категорий, %."""
        total = Allocation.objects.filter(budget_month=self).aggregate(
            total=Sum("percent")
        )["total"]
        return total if total is not None else 0

    @property
    def planned_total_percent(self) -> int:
        """Σ долей категорий и «отложить»; цель — 100."""
        return self.allocations_total_percent + self.savings_percent


class Allocation(models.Model):
    """Плановая доля категории в бюджете месяца."""

    budget_month = models.ForeignKey(
        BudgetMonth,
        on_delete=models.CASCADE,
        related_name="allocations",
        verbose_name="бюджетный месяц",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="allocations",
        verbose_name="категория",
    )
    percent = models.PositiveSmallIntegerField(
        "доля, % от дохода",
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    class Meta:
        verbose_name = "распределение"
        verbose_name_plural = "распределение"
        ordering = ["category__position", "category__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["budget_month", "category"],
                name="unique_allocation_per_month",
            ),
            models.CheckConstraint(
                condition=Q(percent__gte=0) & Q(percent__lte=100),
                name="allocation_percent_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category} — {self.percent} %"

    @property
    def amount(self) -> Decimal:
        """План в рублях: доход месяца × доля."""
        return planned_amount(self.budget_month.income, self.percent)

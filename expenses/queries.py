"""Выборки трат по периодам.

Обычные функции вместо методов кастомного QuerySet: так проще и с типами
(менеджер `Transaction.objects` типизирован стандартными методами), и для
будущих агрегатов (Фаза 6).
"""
from calendar import monthrange
from datetime import date

from django.db import models

from .models import Transaction


def transactions_for_month(year: int, month: int) -> models.QuerySet[Transaction]:
    """Траты за календарный месяц."""
    last_day = monthrange(year, month)[1]
    return Transaction.objects.filter(
        date__range=(date(year, month, 1), date(year, month, last_day))
    )


def transactions_for_period(start: date, end: date) -> models.QuerySet[Transaction]:
    """Траты за период [start, end] включительно."""
    return Transaction.objects.filter(date__range=(start, end))

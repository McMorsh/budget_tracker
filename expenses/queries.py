"""Выборки трат по периодам и предупреждение о перерасходе плана.

Все выборки - в пределах владельца: чужие траты не видны нигде.
Обычные функции вместо методов кастомного QuerySet: так проще и с типами
(менеджер `Transaction.objects` типизирован стандартными методами).
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models

from budget.models import Allocation, BudgetMonth

from .models import Transaction


def transactions_for_month(
    year: int, month: int, owner: User
) -> models.QuerySet[Transaction]:
    """Траты владельца за календарный месяц."""
    last_day = monthrange(year, month)[1]
    return Transaction.objects.filter(
        owner=owner, date__range=(date(year, month, 1), date(year, month, last_day))
    )


def transactions_for_period(
    start: date, end: date, owner: User
) -> models.QuerySet[Transaction]:
    """Траты владельца за период [start, end] включительно."""
    return Transaction.objects.filter(owner=owner, date__range=(start, end))


def category_overrun(transaction: Transaction) -> tuple[Decimal, Decimal] | None:
    """План и факт по категории траты, если факт превысил план.

    Args:
        transaction: Сохранённая трата - месяц и категория берутся из неё.

    Returns:
        Кортеж "план, факт" в рублях, если план заполнен и превышен, иначе
        None (в том числе когда бюджета на месяц или доли категории нет).
    """
    budget_month = BudgetMonth.objects.filter(
        owner=transaction.owner,
        year=transaction.date.year,
        month=transaction.date.month,
    ).first()
    if budget_month is None:
        return None
    allocation = (
        Allocation.objects.filter(
            budget_month=budget_month, category=transaction.category
        )
        .select_related("budget_month")
        .first()
    )
    if allocation is None:
        return None
    plan = allocation.amount
    if plan <= 0:
        return None
    fact = transactions_for_month(
        transaction.date.year, transaction.date.month, transaction.owner
    ).filter(category=transaction.category).aggregate(total=models.Sum("amount"))[
        "total"
    ]
    fact = fact if fact is not None else Decimal("0")
    if fact <= plan:
        return None
    return plan, fact

"""Представления аналитики (пока — обзорная страница)."""
from decimal import Decimal

from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from budget.models import BudgetMonth
from expenses.queries import transactions_for_month
from purchases.models import PlannedPurchase


def home(request: HttpRequest) -> HttpResponse:
    """Обзор: текущий месяц и цели покупок."""
    today = timezone.localdate()
    budget_month = BudgetMonth.objects.filter(year=today.year, month=today.month).first()

    spent = transactions_for_month(today.year, today.month).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")

    free = None
    if budget_month is not None:
        free = budget_month.income - budget_month.savings_amount - spent

    # Аннотация: накопления по целям считаются одним запросом, а не по запросу
    # на каждую цель в шаблоне (см. PlannedPurchase.contributed).
    goals = list(
        PlannedPurchase.objects.filter(status=PlannedPurchase.Status.SAVING).annotate(
            contributed_total=Coalesce(
                Sum("contributions__amount"),
                Value(Decimal("0")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )
    goals_remaining = sum((goal.remaining for goal in goals), Decimal("0"))

    context = {
        "budget_month": budget_month,
        "spent": spent,
        "free": free,
        "goals": goals,
        "goals_remaining": goals_remaining,
    }
    return render(request, "home.html", context)

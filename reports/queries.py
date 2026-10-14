"""Сводки для отчётов: бюджет/траты за месяц и итоги года.

Только чтение и расчёты; страницы - в `reports/views.py`. Бюджет категории -
доход месяца × доля (`planned_amount`), траты - сумма операций. Остаток
положительный, если бюджет не израсходован; отрицательный - перерасход.
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.models import User
from django.db.models import QuerySet, Sum
from django.db.models.functions import TruncMonth
from django.utils.formats import date_format

from budget.models import Allocation, BudgetMonth, Category, planned_amount
from budget.utils import month_title
from expenses.queries import transactions_for_month, transactions_for_period

ZERO = Decimal("0.00")


@dataclass
class CategoryTotal:
    """Бюджет и траты по категории за период."""

    category: Category
    planned: Decimal
    fact: Decimal

    @property
    def remaining(self) -> Decimal:
        """Остаток бюджета: бюджет - траты; отрицательный - перерасход."""
        return self.planned - self.fact

    @property
    def has_plan(self) -> bool:
        """Есть ли у категории бюджет (иначе процент исполнения не считаем)."""
        return self.planned > 0

    @property
    def used_percent(self) -> int:
        """Сколько процентов бюджета израсходовано; 0, если бюджета нет."""
        if not self.has_plan:
            return 0
        value = self.fact / self.planned * 100
        return int(value.to_integral_value(rounding=ROUND_HALF_UP))

    @property
    def bar_percent(self) -> int:
        """Ширина полосы прогресса, 0-100 % (перерасход не расширяет полосу)."""
        return min(self.used_percent, 100)


@dataclass
class MonthReport:
    """Сводка "бюджет/траты" за месяц."""

    year: int
    month: int
    budget_month: BudgetMonth | None
    income: Decimal
    savings: Decimal
    planned: Decimal
    spent: Decimal
    planned_percent: int
    rows: list[CategoryTotal]

    @property
    def title(self) -> str:
        """Название месяца по-русски, например "Сентябрь 2026"."""
        return month_title(self.year, self.month)

    @property
    def remaining(self) -> Decimal:
        """Остаток бюджета: бюджет - траты по категориям."""
        return self.planned - self.spent

    @property
    def free(self) -> Decimal | None:
        """Свободно от дохода: доход - "отложить" - траты.

        None, если бюджета на месяц нет: без дохода разница не имеет смысла.
        """
        if self.budget_month is None:
            return None
        return self.income - self.savings - self.spent


@dataclass
class MonthTotal:
    """Итоги одного месяца года."""

    year: int
    month: int
    income: Decimal
    planned: Decimal
    spent: Decimal

    @property
    def title(self) -> str:
        """Название месяца без года, например "Январь"."""
        return date_format(date(self.year, self.month, 1), "F")

    @property
    def remaining(self) -> Decimal:
        """Остаток бюджета: бюджет - траты."""
        return self.planned - self.spent


@dataclass
class YearReport:
    """Итоги года: месяцы и категории."""

    year: int
    months: list[MonthTotal]
    rows: list[CategoryTotal]
    income: Decimal
    planned: Decimal
    spent: Decimal

    @property
    def remaining(self) -> Decimal:
        """Остаток бюджета за год: бюджет - траты."""
        return self.planned - self.spent


def _facts_by_category(transactions: QuerySet) -> dict[int, Decimal]:
    """Суммы трат по категориям: {id категории: сумма}."""
    rows = transactions.values("category").annotate(total=Sum("amount"))
    return {row["category"]: row["total"] for row in rows}


def _percents_by_category(budget_month: BudgetMonth) -> dict[int, int]:
    """Доли категорий месяца: {id категории: процент}."""
    rows = Allocation.objects.filter(budget_month=budget_month).values(
        "category", "percent"
    )
    return {row["category"]: row["percent"] for row in rows}


def _category_rows(
    facts: dict[int, Decimal], planned: dict[int, Decimal], owner: User
) -> list[CategoryTotal]:
    """Строки по категориям владельца в порядке вывода (`Category.Meta.ordering`)."""
    category_ids = set(facts) | set(planned)
    return [
        CategoryTotal(
            category=category,
            planned=planned.get(category.pk, ZERO),
            fact=facts.get(category.pk, ZERO),
        )
        for category in Category.objects.filter(pk__in=category_ids, owner=owner)
    ]


def month_report(year: int, month: int, owner: User) -> MonthReport:
    """Сводка "бюджет/траты" владельца за календарный месяц."""
    budget_month = BudgetMonth.objects.filter(
        year=year, month=month, owner=owner
    ).first()
    facts = _facts_by_category(transactions_for_month(year, month, owner))

    income = ZERO
    savings = ZERO
    total_percent = 0
    planned: dict[int, Decimal] = {}
    if budget_month is not None:
        income = budget_month.income
        savings = budget_month.savings_amount
        percents = _percents_by_category(budget_month)
        total_percent = budget_month.savings_percent + sum(percents.values())
        for category_id, percent in percents.items():
            planned[category_id] = planned_amount(income, percent)

    rows = _category_rows(facts, planned, owner)
    return MonthReport(
        year=year,
        month=month,
        budget_month=budget_month,
        income=income,
        savings=savings,
        planned=sum((row.planned for row in rows), ZERO),
        spent=sum((row.fact for row in rows), ZERO),
        planned_percent=total_percent,
        rows=rows,
    )


def year_report(year: int, owner: User) -> YearReport:
    """Сводка владельца за год: по месяцам и по категориям.

    Годовой бюджет - сумма округлённых месячных сумм (как на месячных
    экранах), а не округление годового итога. Месяцы без бюджета и трат
    в список не попадают - таблица и график остаются компактными.
    """
    budget_months = {
        budget_month.month: budget_month
        for budget_month in BudgetMonth.objects.filter(year=year, owner=owner)
    }

    planned_by_month: dict[int, Decimal] = {}
    planned_by_category: dict[int, Decimal] = {}
    allocations = Allocation.objects.filter(
        budget_month__year=year, budget_month__owner=owner
    ).select_related("budget_month", "category")
    for allocation in allocations:
        month_number = allocation.budget_month.month
        amount = allocation.amount
        planned_by_month[month_number] = (
            planned_by_month.get(month_number, ZERO) + amount
        )
        category_id = allocation.category.pk
        planned_by_category[category_id] = (
            planned_by_category.get(category_id, ZERO) + amount
        )

    transactions = transactions_for_period(date(year, 1, 1), date(year, 12, 31), owner)
    facts = _facts_by_category(transactions)
    facts_by_month = {
        row["period"].month: row["total"]
        for row in transactions.annotate(period=TruncMonth("date"))
        .values("period")
        .annotate(total=Sum("amount"))
    }

    months = [
        MonthTotal(
            year=year,
            month=month_number,
            income=(
                budget_months[month_number].income
                if month_number in budget_months
                else ZERO
            ),
            planned=planned_by_month.get(month_number, ZERO),
            spent=facts_by_month.get(month_number, ZERO),
        )
        for month_number in sorted(set(budget_months) | set(facts_by_month))
    ]

    return YearReport(
        year=year,
        months=months,
        rows=_category_rows(facts, planned_by_category, owner),
        income=sum((month.income for month in months), ZERO),
        planned=sum((month.planned for month in months), ZERO),
        spent=sum((month.spent for month in months), ZERO),
    )

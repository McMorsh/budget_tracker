"""Представления аналитики: обзор, отчёты и PDF.

`home` — обзорная страница (текущий месяц и цели покупок), остальные —
отчёты за месяц и за год; данные готовит `reports/queries.py`, графики
рисует `static/js/reports.js` по json_script-блокам, PDF собирает
`reports/pdf.py`.
"""
from decimal import Decimal

from django.contrib import messages
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from budget.models import BudgetMonth
from budget.utils import (
    MAX_YEAR,
    MIN_YEAR,
    check_month,
    check_year,
    month_title,
    shift_month,
)
from expenses.queries import transactions_for_month
from purchases.models import PlannedPurchase

from . import pdf, queries

PDF_HINT = (
    "PDF-отчёт недоступен: не установлены зависимости (WeasyPrint, "
    "matplotlib). Пересоберите образ: podman-compose up --build -d."
)


def home(request: HttpRequest) -> HttpResponse:
    """Обзор: текущий месяц и цели покупок."""
    today = timezone.localdate()
    budget_month = BudgetMonth.objects.filter(
        year=today.year, month=today.month
    ).first()

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


def index(request: HttpRequest) -> HttpResponse:
    """Отчёт «план/факт» за текущий месяц."""
    today = timezone.localdate()
    return _month_screen(request, today.year, today.month)


def month(request: HttpRequest, year: int, month: int) -> HttpResponse:
    """Отчёт «план/факт» за конкретный месяц."""
    check_month(year, month)
    return _month_screen(request, year, month)


def _back_month(request: HttpRequest, year: int, report: queries.YearReport) -> int:
    """Месяц для кнопки «К месячному отчёту».

    Если пришли с месячного отчёта — месяц из параметра `month`; иначе
    текущий месяц того же года, последний месяц с данными или декабрь.
    """
    raw = request.GET.get("month", "")
    # isdecimal, а не isdigit: «²».isdigit() истинно, но int() на нём падает.
    if raw.isdecimal() and 1 <= int(raw) <= 12:
        return int(raw)
    today = timezone.localdate()
    if year == today.year:
        return today.month
    if report.months:
        return report.months[-1].month
    return 12


def year(request: HttpRequest, year: int) -> HttpResponse:
    """Итоги года: таблицы по месяцам и категориям, графики."""
    check_year(year)
    report = queries.year_report(year)
    fact_rows = [row for row in report.rows if row.fact > 0]

    context = {
        "report": report,
        "back_month": _back_month(request, year, report),
        "prev_year": year - 1,
        "next_year": year + 1,
        "can_prev": year > MIN_YEAR,
        "can_next": year < MAX_YEAR,
        # Данные графиков — float только для JSON (см. пояснение
        # в _month_screen), в таблицах суммы остаются Decimal.
        "month_chart": {
            "labels": [month_total.title for month_total in report.months],
            "planned": [float(month_total.planned) for month_total in report.months],
            "fact": [float(month_total.spent) for month_total in report.months],
        },
        "structure_chart": {
            "labels": [row.category.name for row in fact_rows],
            "fact": [float(row.fact) for row in fact_rows],
        },
    }
    return render(request, "reports/year.html", context)


def pdf_report(request: HttpRequest, year: int, month: int) -> FileResponse | HttpResponse:
    """PDF-отчёт за месяц: собирает файл в media и отдаёт его на скачивание.

    Если WeasyPrint/matplotlib не установлены (например, образ собран до
    добавления зависимостей), вместо 500 показываем подсказку.
    """
    check_month(year, month)
    try:
        path = pdf.build_report_pdf(year, month)
    except ImportError:
        messages.error(request, PDF_HINT)
        return redirect("reports:month", year=year, month=month)
    return FileResponse(
        path.open("rb"),
        as_attachment=True,
        filename=f"budget-report-{year}-{month:02d}.pdf",
    )


def pdf_year_report(request: HttpRequest, year: int) -> FileResponse | HttpResponse:
    """PDF-отчёт за год: собирает файл в media и отдаёт его на скачивание."""
    check_year(year)
    try:
        path = pdf.build_year_pdf(year)
    except ImportError:
        messages.error(request, PDF_HINT)
        return redirect("reports:year", year=year)
    return FileResponse(
        path.open("rb"),
        as_attachment=True,
        filename=f"budget-report-{year}.pdf",
    )


def _month_screen(request: HttpRequest, year: int, month: int) -> HttpResponse:
    """Общий рендер отчёта за месяц (индекс и конкретный месяц)."""
    report = queries.month_report(year, month)
    prev_year, prev_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)

    context = {
        "report": report,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "prev_title": month_title(prev_year, prev_month),
        "next_year": next_year,
        "next_month": next_month,
        "next_title": month_title(next_year, next_month),
        # На границах диапазона стрелки ведут в 404 — прячем их.
        "can_prev": (year, month) > (MIN_YEAR, 1),
        "can_next": (year, month) < (MAX_YEAR, 12),
        # float — только для JSON: Chart.js принимает числа, а json_script
        # сериализовал бы Decimal строкой. В таблицах суммы остаются Decimal.
        "chart": {
            "labels": [row.category.name for row in report.rows],
            "planned": [float(row.planned) for row in report.rows],
            "fact": [float(row.fact) for row in report.rows],
        },
    }
    return render(request, "reports/month.html", context)

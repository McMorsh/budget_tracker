"""Представления раздела «Траты»: ввод и список за месяц.

Месяц траты определяется её датой (отдельного поля «месяц» нет): форма
ввода подставляет дату по просматриваемому месяцу, а сохранение уводит
на месяц, в который попала дата.

Добавление и удаление — обычные POST с редиректом (PRG). Правка строки —
инлайн через JSON-эндпоинт; после неё страница перезапрашивает таблицу,
поэтому порядок строк и итоги всегда совпадают с базой.
"""
import json
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format, number_format
from django.views.decorators.http import require_POST

from budget.utils import MAX_YEAR, MIN_YEAR, check_month, month_title, shift_month

from .forms import TransactionForm
from .models import Transaction
from .queries import transactions_for_month


def index(request: HttpRequest) -> HttpResponse:
    """Страница текущего месяца."""
    today = timezone.localdate()
    return _month_screen(request, today.year, today.month)


def month_detail(request: HttpRequest, year: int, month: int) -> HttpResponse:
    """Страница конкретного месяца."""
    check_month(year, month)
    return _month_screen(request, year, month)


def _default_date(year: int, month: int) -> date:
    """Дата для быстрого ввода.

    Текущий месяц — сегодняшний день; прошедший — последний день месяца
    (обычно его и добирают задним числом); будущий — первое число.
    """
    today = timezone.localdate()
    if (year, month) == (today.year, today.month):
        return today
    if (year, month) < (today.year, today.month):
        return date(year, month, monthrange(year, month)[1])
    return date(year, month, 1)


def _amount_text(amount: Decimal) -> str:
    """Сумма по-русски: «1 234,50 ₽»."""
    return f"{number_format(amount, decimal_pos=2, force_grouping=True)} ₽"


def _month_screen(request: HttpRequest, year: int, month: int) -> HttpResponse:
    """Форма быстрого ввода и список трат месяца."""
    form = TransactionForm(
        request.POST or None, initial={"date": _default_date(year, month)}
    )
    if request.method == "POST" and form.is_valid():
        item = form.save()
        messages.success(
            request,
            f"Трата добавлена: {_amount_text(item.amount)} — {item.category.name}.",
        )
        return redirect("expenses:month", item.date.year, item.date.month)

    items = list(transactions_for_month(year, month).select_related("category"))
    total = sum((item.amount for item in items), Decimal("0"))

    prev_year, prev_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)

    context = {
        "form": form,
        "year": year,
        "month": month,
        "month_title": month_title(year, month),
        "prev_year": prev_year,
        "prev_month": prev_month,
        "prev_title": month_title(prev_year, prev_month),
        "next_year": next_year,
        "next_month": next_month,
        "next_title": month_title(next_year, next_month),
        # На границах диапазона стрелки ведут в 404 — прячем их.
        "can_prev": (year, month) > (MIN_YEAR, 1),
        "can_next": (year, month) < (MAX_YEAR, 12),
        "items": items,
        "count": len(items),
        "total": total,
    }
    return render(request, "expenses/month.html", context)


def _json_payload(request: HttpRequest) -> dict | None:
    """JSON-тело запроса; None, если это не JSON-объект."""
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _first_error(form: TransactionForm) -> tuple[str, str]:
    """(поле, сообщение) первой ошибки формы — для JSON-ответа."""
    for name, errors in form.errors.items():
        if errors:
            return name, str(errors[0])
    return "", "Проверьте данные"


@require_POST
def transaction_update(request: HttpRequest, pk: int) -> JsonResponse:
    """Инлайн-правка траты (AJAX)."""
    # select_related: форма в __init__ обращается к instance.category
    # (архивную категорию нужно оставить доступной).
    item = get_object_or_404(Transaction.objects.select_related("category"), pk=pk)
    payload = _json_payload(request)
    if payload is None:
        return JsonResponse({"error": "Ожидается JSON-объект"}, status=400)

    form = TransactionForm(payload, instance=item)
    if not form.is_valid():
        field, error = _first_error(form)
        return JsonResponse({"error": error, "field": field}, status=400)

    item = form.save()
    return JsonResponse(
        {
            "ok": True,
            "transaction": {
                "id": item.pk,
                "date": item.date.isoformat(),
                "date_text": date_format(item.date, "d.m.Y"),
                "category_id": item.category.pk,
                "category_name": item.category.name,
                "amount": str(item.amount),
                "comment": item.comment,
            },
            "month_url": reverse(
                "expenses:month", args=[item.date.year, item.date.month]
            ),
        }
    )


@require_POST
def transaction_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Удаление траты с возвратом на месяц, в котором она была."""
    item = get_object_or_404(Transaction, pk=pk)
    year, month = item.date.year, item.date.month
    item.delete()
    messages.success(request, "Трата удалена.")
    return redirect("expenses:month", year, month)

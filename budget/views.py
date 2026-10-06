"""Представления раздела «Бюджет»: распределение месяца и категории.

Категории редактируются прямо в списке (AJAX), план месяца сохраняется обычной
формой: доход, «отложить» и доли категорий. Плановые суммы в рублях —
производные: доход × доля (округление до копеек).
"""
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Max, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import number_format
from django.views.decorators.http import require_POST

from budget.utils import MAX_YEAR, MIN_YEAR, check_month, month_title, shift_month

from .forms import CategoryForm, MonthPlanForm
from .models import Allocation, BudgetMonth, Category, money

FULL_PERCENT = 100


def index(request: HttpRequest) -> HttpResponse:
    """Экран текущего месяца."""
    today = timezone.localdate()
    return _month_screen(request, today.year, today.month)


def month_detail(request: HttpRequest, year: int, month: int) -> HttpResponse:
    """Экран конкретного месяца."""
    check_month(year, month)
    return _month_screen(request, year, month)


def _as_decimal(value) -> Decimal:
    """Значение поля формы в Decimal (пустое и нечитаемое → 0)."""
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _as_int(value) -> int:
    """Значение поля формы в int (пустое и нечитаемое → 0)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _balance_text(remaining: Decimal) -> str:
    amount = number_format(abs(remaining), decimal_pos=2, force_grouping=True)
    if remaining < 0:
        return f"Перерасход: {amount} ₽"
    return f"Свободно от дохода: {amount} ₽"


def _add_balance_warning(request: HttpRequest, budget_month: BudgetMonth) -> None:
    """Предупреждение, если план не сходится со 100 % (сохраняем всё равно)."""
    total = budget_month.planned_total_percent
    if total == FULL_PERCENT:
        return
    gap = FULL_PERCENT - total
    if gap > 0:
        messages.warning(
            request,
            f"Σ долей = {total} % — до 100 % не хватает {gap} %.",
        )
    else:
        excess = money(budget_month.income * (-gap) / 100)
        messages.warning(
            request,
            f"Σ долей = {total} % — перерасход плана на "
            f"{number_format(excess, decimal_pos=2, force_grouping=True)} ₽.",
        )


def _month_screen(request: HttpRequest, year: int, month: int) -> HttpResponse:
    """Экран месяца: доход, доли категорий и «отложить»."""
    budget_month = BudgetMonth.objects.filter(year=year, month=month).first()

    category_filter = Q(is_active=True)
    if budget_month is not None:
        category_filter |= Q(allocations__budget_month=budget_month)
    categories = list(Category.objects.filter(category_filter).distinct())

    if request.method == "POST":
        form = MonthPlanForm(request.POST, categories=categories)
        if form.is_valid():
            budget_month, _created = BudgetMonth.objects.get_or_create(
                year=year, month=month
            )
            budget_month.income = form.cleaned_data["income"]
            budget_month.savings_percent = form.cleaned_data["savings_percent"]
            budget_month.save(update_fields=["income", "savings_percent"])
            with transaction.atomic():
                for category in categories:
                    percent = form.cleaned_data[f"percent_{category.pk}"]
                    if percent:
                        Allocation.objects.update_or_create(
                            budget_month=budget_month,
                            category=category,
                            defaults={"percent": percent},
                        )
                    else:
                        Allocation.objects.filter(
                            budget_month=budget_month, category=category
                        ).delete()
            messages.success(request, "План месяца сохранён.")
            _add_balance_warning(request, budget_month)
            return redirect(request.path)
    else:
        initial: dict[str, object] = {
            "income": budget_month.income if budget_month else Decimal("0"),
            "savings_percent": (
                budget_month.savings_percent if budget_month else Decimal("0")
            ),
        }
        if budget_month is not None:
            allocations = Allocation.objects.filter(
                budget_month=budget_month
            ).select_related("category")
            for allocation in allocations:
                initial[f"percent_{allocation.category.pk}"] = allocation.percent
        form = MonthPlanForm(categories=categories, initial=initial)

    income = _as_decimal(form["income"].value())
    savings_percent = _as_int(form["savings_percent"].value())

    sum_percent = savings_percent
    total_amount = money(income * savings_percent / 100)
    savings_amount = total_amount
    rows = []
    for category in categories:
        field = form[f"percent_{category.pk}"]
        percent = _as_int(field.value())
        amount = money(income * percent / 100)
        rows.append(
            {
                "category": category,
                "field": field,
                "amount": amount,
                "archived": not category.is_active,
            }
        )
        sum_percent += percent
        total_amount += amount

    remaining = income - total_amount

    prev_year, prev_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)
    copy_source = BudgetMonth.objects.filter(year=prev_year, month=prev_month).first()

    context = {
        "form": form,
        "budget_month": budget_month,
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
        "copy_source": copy_source,
        "rows": rows,
        "savings_amount": savings_amount,
        "sum_percent": sum_percent,
        "total_amount": total_amount,
        "balanced": sum_percent == FULL_PERCENT,
        "remaining_negative": remaining < 0,
        "balance_text": _balance_text(remaining),
    }
    return render(request, "budget/month.html", context)


@require_POST
def month_copy(request: HttpRequest, year: int, month: int) -> HttpResponse:
    """Копирует доход и распределение из предыдущего месяца."""
    check_month(year, month)

    prev_year, prev_month = shift_month(year, month, -1)
    source = BudgetMonth.objects.filter(year=prev_year, month=prev_month).first()
    if source is None:
        messages.warning(request, "Предыдущий месяц не заполнен — копировать нечего.")
        return redirect("budget:month", year=year, month=month)

    target, _created = BudgetMonth.objects.get_or_create(year=year, month=month)
    with transaction.atomic():
        target.income = source.income
        target.savings_percent = source.savings_percent
        target.save(update_fields=["income", "savings_percent"])
        Allocation.objects.filter(budget_month=target).delete()
        Allocation.objects.bulk_create(
            [
                Allocation(
                    budget_month=target,
                    category=allocation.category,
                    percent=allocation.percent,
                )
                for allocation in Allocation.objects.filter(budget_month=source)
            ]
        )
    messages.success(request, f"Скопировано из «{source.title}».")
    return redirect("budget:month", year=year, month=month)


def category_list(request: HttpRequest) -> HttpResponse:
    """Список категорий: активные (с перетаскиванием) и архив."""
    context = {
        "active_categories": Category.objects.filter(is_active=True),
        "archived_categories": Category.objects.filter(is_active=False),
    }
    return render(request, "budget/category_list.html", context)


def _json_payload(request: HttpRequest) -> dict:
    """Разбирает JSON-тело запроса; пустой словарь, если это не JSON-объект."""
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _first_error(form: CategoryForm) -> str:
    """Первое сообщение об ошибке формы — для JSON-ответа."""
    for errors in form.errors.values():
        if errors:
            return str(errors[0])
    return "Проверьте название"


@require_POST
def category_create(request: HttpRequest) -> JsonResponse:
    """Добавляет категорию (AJAX): порядок — в конец списка."""
    form = CategoryForm(_json_payload(request))
    if not form.is_valid():
        return JsonResponse({"error": _first_error(form)}, status=400)

    category = form.save(commit=False)
    last_position = Category.objects.aggregate(max_position=Max("position"))[
        "max_position"
    ]
    category.position = 0 if last_position is None else last_position + 1
    category.save()
    return JsonResponse(
        {
            "ok": True,
            "id": category.pk,
            "name": category.name,
            "toggle_url": reverse("budget:category_toggle", args=[category.pk]),
        }
    )


@require_POST
def category_rename(request: HttpRequest) -> JsonResponse:
    """Переименование из списка (AJAX, двойной клик по названию)."""
    payload = _json_payload(request)
    try:
        pk = int(payload["id"])
    except (KeyError, TypeError, ValueError):
        return JsonResponse(
            {"error": 'Ожидается JSON вида {"id": 1, "name": "…"}'}, status=400
        )

    category = Category.objects.filter(pk=pk).first()
    if category is None:
        return JsonResponse({"error": "Категория не найдена"}, status=404)

    form = CategoryForm({"name": payload.get("name", "")}, instance=category)
    if not form.is_valid():
        return JsonResponse({"error": _first_error(form)}, status=400)

    form.save()
    return JsonResponse({"ok": True, "id": category.pk, "name": category.name})


@require_POST
def category_reorder(request: HttpRequest) -> JsonResponse:
    """Сохраняет порядок активных категорий, заданный перетаскиванием."""
    try:
        payload = json.loads(request.body)
        ids = [int(pk) for pk in payload["ids"]]
    except (KeyError, TypeError, ValueError):
        return JsonResponse(
            {"error": 'Ожидается JSON вида {"ids": [1, 2, 3]}'}, status=400
        )

    with transaction.atomic():
        for position, pk in enumerate(ids):
            Category.objects.filter(pk=pk).update(position=position)
    return JsonResponse({"ok": True, "count": len(ids)})


@require_POST
def category_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    """Архивация и возврат из архива: удаления нет, история трат сохраняется."""
    category = get_object_or_404(Category, pk=pk)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active"])
    if category.is_active:
        messages.success(request, f"Категория «{category.name}» возвращена в работу.")
    else:
        messages.info(
            request,
            f"Категория «{category.name}» в архиве; история трат сохранена.",
        )
    return redirect("budget:categories")

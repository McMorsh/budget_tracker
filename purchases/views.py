"""Представления раздела «Покупки»: цели, взносы и прогресс.

Добавление целей и взносов, удаления — обычные POST с редиректом (PRG).
Правка строк — инлайн через JSON-эндпоинты; после неё список или карточка
цели перезапрашиваются с сервера, поэтому порядок целей, прогресс и итоги
всегда совпадают с базой (тот же приём, что в «Тратах»).
"""
from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from budget.templatetags.money import rubles
from common.http import first_error, json_payload

from .forms import ContributionForm, PlannedPurchaseForm
from .models import PlannedPurchase, PurchaseContribution
from .queries import goals_with_contributed

# Статусы, которые показываются в списке активных целей; «куплено» —
# отдельной таблицей, у неё свой порядок (по дате покупки).
ACTIVE_STATUSES = [PlannedPurchase.Status.WANTED, PlannedPurchase.Status.SAVING]


def index(request: HttpRequest) -> HttpResponse:
    """Список целей: активные и уже купленные, плюс форма добавления."""
    form = PlannedPurchaseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        purchase = form.save()
        messages.success(request, f"Цель добавлена: {purchase.title}.")
        return redirect("purchases:index")

    goals = list(goals_with_contributed().filter(status__in=ACTIVE_STATUSES))
    bought = list(
        goals_with_contributed()
        .filter(status=PlannedPurchase.Status.BOUGHT)
        .order_by("-bought_at", "-pk")
    )
    totals = {
        "amount": sum((goal.amount for goal in goals), Decimal("0")),
        "contributed": sum((goal.contributed for goal in goals), Decimal("0")),
        "remaining": sum((goal.remaining for goal in goals), Decimal("0")),
    }

    context = {
        "form": form,
        "goals": goals,
        "bought": bought,
        "totals": totals,
    }
    return render(request, "purchases/list.html", context)


def detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Карточка цели: прогресс, взносы и форма нового взноса."""
    goal = get_object_or_404(goals_with_contributed(), pk=pk)
    form = ContributionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        contribution = form.save(commit=False)
        contribution.purchase = goal
        contribution.save()
        messages.success(
            request, f"Взнос добавлен: {rubles(contribution.amount, 2)}."
        )
        return redirect("purchases:detail", pk)

    contributions = list(PurchaseContribution.objects.filter(purchase=goal))
    contributions_total = sum((item.amount for item in contributions), Decimal("0"))

    context = {
        "goal": goal,
        "form": form,
        "contributions": contributions,
        "contributions_total": contributions_total,
    }
    return render(request, "purchases/detail.html", context)


@require_POST
def purchase_update(request: HttpRequest, pk: int) -> JsonResponse:
    """Инлайн-правка цели (AJAX): название, стоимость, приоритет, статус.

    Ответ — `{"ok": true}`; ошибки — 400 с `error` и `field`, чужой pk — 404.
    """
    goal = get_object_or_404(PlannedPurchase, pk=pk)
    payload = json_payload(request)
    if payload is None:
        return JsonResponse({"error": "Ожидается JSON-объект"}, status=400)

    form = PlannedPurchaseForm(payload, instance=goal)
    if not form.is_valid():
        field, error = first_error(form)
        return JsonResponse({"error": error, "field": field}, status=400)

    form.save()
    return JsonResponse({"ok": True})


@require_POST
def purchase_status(request: HttpRequest, pk: int) -> JsonResponse:
    """Смена статуса кнопками списка или карточки (AJAX).

    Дату покупки проставляет или снимает `PlannedPurchase.save()` — держать
    эту логику в двух местах не нужно. Ответ — `{"ok": true}`; ошибки —
    400 с `error` и `field`, чужой pk — 404.
    """
    goal = get_object_or_404(PlannedPurchase, pk=pk)
    payload = json_payload(request)
    if payload is None:
        return JsonResponse({"error": "Ожидается JSON-объект"}, status=400)

    status = payload.get("status")
    if not isinstance(status, str) or status not in PlannedPurchase.Status.values:
        return JsonResponse(
            {"error": "Неизвестный статус", "field": "status"}, status=400
        )

    goal.status = status
    goal.save()
    return JsonResponse({"ok": True, "status": goal.status})


@require_POST
def purchase_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Удаление цели вместе со взносами (каскадом)."""
    goal = get_object_or_404(PlannedPurchase, pk=pk)
    title = goal.title
    goal.delete()
    messages.success(request, f"Цель удалена: {title}.")
    return redirect("purchases:index")


@require_POST
def contribution_update(request: HttpRequest, pk: int) -> JsonResponse:
    """Инлайн-правка взноса (AJAX).

    Ответ — `{"ok": true}`; ошибки — 400 с `error` и `field`, чужой pk — 404.
    """
    item = get_object_or_404(PurchaseContribution, pk=pk)
    payload = json_payload(request)
    if payload is None:
        return JsonResponse({"error": "Ожидается JSON-объект"}, status=400)

    form = ContributionForm(payload, instance=item)
    if not form.is_valid():
        field, error = first_error(form)
        return JsonResponse({"error": error, "field": field}, status=400)

    form.save()
    return JsonResponse({"ok": True})


@require_POST
def contribution_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Удаление взноса с возвратом в карточку цели."""
    item = get_object_or_404(PurchaseContribution, pk=pk)
    purchase_pk = item.purchase.pk
    item.delete()
    messages.success(request, "Взнос удалён.")
    return redirect("purchases:detail", purchase_pk)

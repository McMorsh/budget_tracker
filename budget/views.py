"""Представления раздела «Бюджет»: категории.

Категории редактируются прямо в списке (AJAX): создание и переименование,
порядок — перетаскиванием, вместо удаления — архивация.
"""
import json

from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import CategoryForm
from .models import Category


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

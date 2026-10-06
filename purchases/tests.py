"""Тесты моделей и экранов раздела «Покупки»."""
import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import PlannedPurchase, PurchaseContribution
from .queries import goals_with_contributed


class PlannedPurchaseTests(TestCase):
    """Тесты моделей: прогресс, валидаторы, статусы и порядок целей."""

    def test_contributed_and_remaining(self):
        purchase = PlannedPurchase.objects.create(
            title="Ноутбук", amount=Decimal("90000")
        )
        PurchaseContribution.objects.create(purchase=purchase, amount=Decimal("15000"))
        PurchaseContribution.objects.create(purchase=purchase, amount=Decimal("5000"))
        self.assertEqual(purchase.contributed, Decimal("20000.00"))
        self.assertEqual(purchase.remaining, Decimal("70000.00"))
        self.assertEqual(purchase.progress_percent, 22)

    def test_default_status_is_wanted(self):
        purchase = PlannedPurchase.objects.create(
            title="Наушники", amount=Decimal("12000")
        )
        self.assertEqual(purchase.status, PlannedPurchase.Status.WANTED)

    def test_negative_amount_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlannedPurchase.objects.create(
                title="Странная покупка", amount=Decimal("-1")
            )

    def test_amount_validator_rejects_negative(self):
        # Валидатор ловит неверную сумму в формах (админка, инлайн-правка),
        # а не только на уровне базы.
        purchase = PlannedPurchase(title="Наушники", amount=Decimal("-1"))
        with self.assertRaises(ValidationError) as ctx:
            purchase.full_clean()
        self.assertIn("amount", ctx.exception.message_dict)

    def test_non_positive_contribution_is_rejected(self):
        purchase = PlannedPurchase.objects.create(
            title="Наушники", amount=Decimal("12000")
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseContribution.objects.create(purchase=purchase, amount=Decimal("0"))

    def test_contribution_amount_validator_rejects_non_positive(self):
        purchase = PlannedPurchase.objects.create(
            title="Наушники", amount=Decimal("12000")
        )
        for amount in [Decimal("0"), Decimal("-5")]:
            with self.subTest(amount=amount):
                contribution = PurchaseContribution(
                    purchase=purchase, amount=amount, date=date(2026, 9, 1)
                )
                with self.assertRaises(ValidationError) as ctx:
                    contribution.full_clean()
                self.assertIn("amount", ctx.exception.message_dict)

    def test_contribution_date_validator_rejects_out_of_range(self):
        purchase = PlannedPurchase.objects.create(
            title="Наушники", amount=Decimal("12000")
        )
        for value in [date(1800, 1, 1), date(2200, 1, 1)]:
            with self.subTest(value=value):
                contribution = PurchaseContribution(
                    purchase=purchase, amount=Decimal("100"), date=value
                )
                with self.assertRaises(ValidationError) as ctx:
                    contribution.full_clean()
                self.assertIn("date", ctx.exception.message_dict)

    def test_contribution_date_accepts_boundaries(self):
        purchase = PlannedPurchase.objects.create(
            title="Наушники", amount=Decimal("12000")
        )
        for value in [date(1900, 1, 1), date(2100, 12, 31)]:
            with self.subTest(value=value):
                contribution = PurchaseContribution(
                    purchase=purchase, amount=Decimal("100"), date=value
                )
                # Границы диапазона включительны — исключений быть не должно.
                contribution.full_clean()

    def test_progress_percent_is_capped_at_100(self):
        purchase = PlannedPurchase.objects.create(
            title="Наушники", amount=Decimal("100")
        )
        PurchaseContribution.objects.create(purchase=purchase, amount=Decimal("150"))
        self.assertEqual(purchase.progress_percent, 100)
        self.assertEqual(purchase.remaining, Decimal("0"))

    def test_progress_percent_of_free_goal_is_zero(self):
        purchase = PlannedPurchase.objects.create(
            title="Наушники", amount=Decimal("0")
        )
        self.assertEqual(purchase.progress_percent, 0)

    def test_progress_percent_truncates_fraction(self):
        purchase = PlannedPurchase.objects.create(
            title="Наушники", amount=Decimal("300")
        )
        PurchaseContribution.objects.create(purchase=purchase, amount=Decimal("200"))
        self.assertEqual(purchase.progress_percent, 66)

    def test_ordering_puts_priority_first(self):
        low = PlannedPurchase.objects.create(title="Низкий", priority=0)
        high = PlannedPurchase.objects.create(title="Высокий", priority=5)
        self.assertEqual(list(PlannedPurchase.objects.all()), [high, low])

    def test_bought_status_sets_bought_date(self):
        purchase = PlannedPurchase.objects.create(
            title="Кресло",
            amount=Decimal("30000"),
            status=PlannedPurchase.Status.BOUGHT,
        )
        self.assertEqual(purchase.bought_at, timezone.localdate())

    def test_leaving_bought_clears_bought_date(self):
        purchase = PlannedPurchase.objects.create(
            title="Кресло",
            amount=Decimal("30000"),
            status=PlannedPurchase.Status.BOUGHT,
        )
        purchase.status = PlannedPurchase.Status.SAVING
        purchase.save()
        purchase.refresh_from_db()
        self.assertIsNone(purchase.bought_at)

    def test_bought_date_is_not_overwritten(self):
        purchase = PlannedPurchase.objects.create(
            title="Кресло",
            amount=Decimal("30000"),
            status=PlannedPurchase.Status.BOUGHT,
            bought_at=date(2026, 5, 1),
        )
        purchase.save()
        purchase.refresh_from_db()
        self.assertEqual(purchase.bought_at, date(2026, 5, 1))

    def test_goals_with_contributed_annotation(self):
        purchase = PlannedPurchase.objects.create(
            title="Ноутбук", amount=Decimal("90000")
        )
        PurchaseContribution.objects.create(purchase=purchase, amount=Decimal("15000"))
        goal = goals_with_contributed().get(pk=purchase.pk)
        self.assertEqual(goal.remaining, Decimal("75000.00"))
        total = (
            goals_with_contributed()
            .filter(pk=purchase.pk)
            .values_list("contributed_total", flat=True)
            .get()
        )
        self.assertEqual(total, Decimal("15000.00"))


class PurchaseViewsTests(TestCase):
    """Список целей, карточка, инлайн-правка, статусы и взносы (Фаза 8)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )

    def setUp(self):
        self.client.force_login(self.user)

    def post_json(self, url: str, payload: dict):
        return self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

    def make_goal(self, **kwargs) -> PlannedPurchase:
        fields = {"title": "Ноутбук", "amount": Decimal("90000")}
        fields.update(kwargs)
        return PlannedPurchase.objects.create(**fields)

    # --- доступ ---

    def test_section_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("purchases:index"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_edit_endpoints_require_login(self):
        goal = self.make_goal()
        contribution = PurchaseContribution.objects.create(
            purchase=goal, amount=Decimal("100")
        )
        self.client.logout()
        urls = [
            reverse("purchases:detail", args=[goal.pk]),
            reverse("purchases:purchase_update", args=[goal.pk]),
            reverse("purchases:purchase_status", args=[goal.pk]),
            reverse("purchases:purchase_delete", args=[goal.pk]),
            reverse("purchases:contribution_update", args=[contribution.pk]),
            reverse("purchases:contribution_delete", args=[contribution.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("login")))

    # --- список ---

    def test_list_empty_state(self):
        response = self.client.get(reverse("purchases:index"))
        self.assertContains(response, "Активных целей нет")
        self.assertEqual(list(response.context["goals"]), [])

    def test_list_shows_active_goal_with_progress(self):
        goal = self.make_goal()
        PurchaseContribution.objects.create(purchase=goal, amount=Decimal("30000"))
        # Вторая цель — чтобы итоги отличались от строки: иначе проверки
        # совпадали бы и со строками, и с tfoot сразу.
        self.make_goal(title="Наушники", amount=Decimal("10000"))

        response = self.client.get(reverse("purchases:index"))
        self.assertContains(response, "Ноутбук")
        self.assertContains(response, "30\xa0000 ₽ из 90\xa0000 ₽")
        self.assertContains(response, "60\xa0000 ₽")  # осталось
        self.assertContains(response, "33 %")  # прогресс

    def test_list_shows_free_goal_without_amount(self):
        self.make_goal(title="Подарок", amount=Decimal("0"))
        saved = self.make_goal(title="Мечта", amount=Decimal("0"))
        PurchaseContribution.objects.create(purchase=saved, amount=Decimal("5000"))

        response = self.client.get(reverse("purchases:index"))
        # Ноль в знаменателе дал бы «0 ₽ из 0 ₽» и ложное «готово»;
        # у свободной цели с накоплениями показываем только их.
        self.assertContains(response, "стоимость не задана")
        self.assertContains(response, "накоплено 5\xa0000 ₽")
        self.assertNotContains(response, "готово")

    def test_list_shows_status_labels(self):
        self.make_goal(title="Хотелка")
        self.make_goal(title="Копилка", status=PlannedPurchase.Status.SAVING)

        response = self.client.get(reverse("purchases:index"))
        # В форме добавления слова «хочу»/«коплю» есть всегда — проверяем
        # подписи в самих строках таблицы.
        self.assertContains(
            response, '<span class="goal-meta muted">хочу</span>', html=False
        )
        self.assertContains(
            response, '<span class="goal-meta muted">коплю</span>', html=False
        )

    def test_list_shows_totals(self):
        first = self.make_goal(title="Ноутбук", amount=Decimal("90000"))
        self.make_goal(title="Наушники", amount=Decimal("10000"))
        PurchaseContribution.objects.create(purchase=first, amount=Decimal("20000"))
        # Купленное в итоги активных целей не входит.
        bought = self.make_goal(
            title="Кресло",
            amount=Decimal("30000"),
            status=PlannedPurchase.Status.BOUGHT,
        )
        PurchaseContribution.objects.create(purchase=bought, amount=Decimal("5000"))

        response = self.client.get(reverse("purchases:index"))
        self.assertContains(response, "20\xa0000 ₽ из 90\xa0000 ₽")
        self.assertContains(response, "70\xa0000 ₽")  # осталось
        self.assertContains(response, "20\xa0000 ₽ из 100\xa0000 ₽")
        self.assertContains(response, "80\xa0000 ₽")  # итого осталось
        self.assertNotContains(response, "25\xa0000 ₽ из 130\xa0000 ₽")
        self.assertNotContains(response, "105\xa0000 ₽")

    def test_list_orders_by_priority(self):
        self.make_goal(title="Низкий", priority=0)
        self.make_goal(title="Высокий", priority=5)

        content = self.client.get(reverse("purchases:index")).content.decode()
        self.assertLess(content.index("Высокий"), content.index("Низкий"))

    def test_list_shows_bought_separately(self):
        self.make_goal(
            title="Кресло",
            amount=Decimal("30000"),
            status=PlannedPurchase.Status.BOUGHT,
        )

        response = self.client.get(reverse("purchases:index"))
        self.assertContains(response, "<h2>Куплено</h2>", html=False)
        self.assertContains(response, "Кресло")
        self.assertContains(response, "за 30\xa0000 ₽")
        self.assertContains(response, "Активных целей нет")

    def test_list_hides_bought_section_when_empty(self):
        self.make_goal()
        response = self.client.get(reverse("purchases:index"))
        self.assertNotContains(response, "<h2>Куплено</h2>", html=False)

    # --- добавление ---

    def test_add_goal(self):
        response = self.client.post(
            reverse("purchases:index"),
            {
                "title": "Ноутбук",
                "amount": "95000",
                "priority": "2",
                "status": "saving",
            },
        )
        self.assertRedirects(response, reverse("purchases:index"))
        goal = PlannedPurchase.objects.get()
        self.assertEqual(goal.title, "Ноутбук")
        self.assertEqual(goal.amount, Decimal("95000.00"))
        self.assertEqual(goal.priority, 2)
        self.assertEqual(goal.status, PlannedPurchase.Status.SAVING)

    def test_add_goal_rejects_blank_title(self):
        response = self.client.post(
            reverse("purchases:index"),
            {"title": "", "amount": "100", "priority": "0", "status": "wanted"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Обязательное")
        self.assertFalse(PlannedPurchase.objects.exists())

    def test_add_goal_rejects_negative_amount(self):
        response = self.client.post(
            reverse("purchases:index"),
            {"title": "Долг", "amount": "-5", "priority": "0", "status": "wanted"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PlannedPurchase.objects.exists())

    def test_add_goal_rejects_unknown_status(self):
        response = self.client.post(
            reverse("purchases:index"),
            {"title": "Ноутбук", "amount": "100", "priority": "0", "status": "zzz"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PlannedPurchase.objects.exists())

    def test_add_goal_rejects_missing_fields(self):
        response = self.client.post(reverse("purchases:index"), {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PlannedPurchase.objects.exists())

    def test_add_goal_accepts_title_max_length(self):
        response = self.client.post(
            reverse("purchases:index"),
            {
                "title": "x" * 200,
                "amount": "100",
                "priority": "0",
                "status": "wanted",
            },
        )
        self.assertRedirects(response, reverse("purchases:index"))

    def test_add_goal_rejects_long_title(self):
        response = self.client.post(
            reverse("purchases:index"),
            {
                "title": "x" * 201,
                "amount": "100",
                "priority": "0",
                "status": "wanted",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PlannedPurchase.objects.exists())

    def test_add_goal_rejects_negative_priority(self):
        response = self.client.post(
            reverse("purchases:index"),
            {
                "title": "Ноутбук",
                "amount": "100",
                "priority": "-1",
                "status": "wanted",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PlannedPurchase.objects.exists())

    def test_add_goal_accepts_max_amount(self):
        response = self.client.post(
            reverse("purchases:index"),
            {
                "title": "Остров",
                "amount": "9999999999.99",
                "priority": "0",
                "status": "wanted",
            },
        )
        self.assertRedirects(response, reverse("purchases:index"))

    def test_add_goal_rejects_amount_above_max_digits(self):
        response = self.client.post(
            reverse("purchases:index"),
            {
                "title": "Остров",
                "amount": "99999999999.99",
                "priority": "0",
                "status": "wanted",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PlannedPurchase.objects.exists())

    # --- инлайн-правка цели ---

    def test_update_goal(self):
        goal = self.make_goal()
        response = self.post_json(
            reverse("purchases:purchase_update", args=[goal.pk]),
            {
                "title": "Игровой ноутбук",
                "amount": "120000",
                "priority": "4",
                "status": goal.status,
            },
        )
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.title, "Игровой ноутбук")
        self.assertEqual(goal.amount, Decimal("120000.00"))
        self.assertEqual(goal.priority, 4)

    def test_update_goal_can_change_status(self):
        goal = self.make_goal()
        response = self.post_json(
            reverse("purchases:purchase_update", args=[goal.pk]),
            {
                "title": goal.title,
                "amount": "90000",
                "priority": "0",
                "status": "bought",
            },
        )
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.status, PlannedPurchase.Status.BOUGHT)
        self.assertEqual(goal.bought_at, timezone.localdate())

    def test_update_goal_reports_field_error(self):
        goal = self.make_goal()
        response = self.post_json(
            reverse("purchases:purchase_update", args=[goal.pk]),
            {"title": "", "amount": "90000", "priority": "0", "status": "wanted"},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["field"], "title")
        self.assertTrue(data["error"])

    def test_update_goal_rejects_bad_json(self):
        goal = self.make_goal()
        url = reverse("purchases:purchase_update", args=[goal.pk])
        response = self.client.post(
            url, data="не json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_update_goal_rejects_non_object_json(self):
        goal = self.make_goal()
        url = reverse("purchases:purchase_update", args=[goal.pk])
        for body in ["null", json.dumps([1, 2])]:
            with self.subTest(body=body):
                response = self.client.post(
                    url, data=body, content_type="application/json"
                )
                self.assertEqual(response.status_code, 400)

    def test_update_goal_rejects_get(self):
        goal = self.make_goal()
        response = self.client.get(
            reverse("purchases:purchase_update", args=[goal.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_update_goal_unknown_is_404(self):
        response = self.post_json(
            reverse("purchases:purchase_update", args=[999]),
            {"title": "X", "amount": "1", "priority": "0", "status": "wanted"},
        )
        self.assertEqual(response.status_code, 404)

    def test_update_goal_requires_csrf_token(self):
        goal = self.make_goal()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.get(reverse("purchases:index"))  # страница ставит cookie csrftoken
        url = reverse("purchases:purchase_update", args=[goal.pk])
        payload = json.dumps(
            {
                "title": "Ноутбук",
                "amount": "90000",
                "priority": "0",
                "status": "wanted",
            }
        )

        without_token = client.post(url, data=payload, content_type="application/json")
        self.assertEqual(without_token.status_code, 403)

        token = client.cookies["csrftoken"].value
        with_token = client.post(
            url,
            data=payload,
            content_type="application/json",
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(with_token.status_code, 200)

    # --- смена статуса ---

    def test_status_to_saving(self):
        goal = self.make_goal()
        response = self.post_json(
            reverse("purchases:purchase_status", args=[goal.pk]), {"status": "saving"}
        )
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.status, PlannedPurchase.Status.SAVING)

    def test_status_to_bought_sets_date(self):
        goal = self.make_goal()
        response = self.post_json(
            reverse("purchases:purchase_status", args=[goal.pk]), {"status": "bought"}
        )
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.status, PlannedPurchase.Status.BOUGHT)
        self.assertEqual(goal.bought_at, timezone.localdate())

    def test_status_back_from_bought_clears_date(self):
        goal = self.make_goal(status=PlannedPurchase.Status.BOUGHT)
        response = self.post_json(
            reverse("purchases:purchase_status", args=[goal.pk]), {"status": "saving"}
        )
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertIsNone(goal.bought_at)

    def test_status_rejects_unknown_value(self):
        goal = self.make_goal()
        response = self.post_json(
            reverse("purchases:purchase_status", args=[goal.pk]), {"status": "zzz"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "status")

    def test_status_rejects_non_object_json(self):
        goal = self.make_goal()
        url = reverse("purchases:purchase_status", args=[goal.pk])
        for body in ["null", json.dumps([1, 2])]:
            with self.subTest(body=body):
                response = self.client.post(
                    url, data=body, content_type="application/json"
                )
                self.assertEqual(response.status_code, 400)

    def test_status_unknown_goal_is_404(self):
        response = self.post_json(
            reverse("purchases:purchase_status", args=[999]), {"status": "saving"}
        )
        self.assertEqual(response.status_code, 404)

    def test_status_rejects_get(self):
        goal = self.make_goal()
        response = self.client.get(
            reverse("purchases:purchase_status", args=[goal.pk])
        )
        self.assertEqual(response.status_code, 405)

    # --- удаление цели ---

    def test_delete_goal_cascades_to_contributions(self):
        goal = self.make_goal()
        PurchaseContribution.objects.create(purchase=goal, amount=Decimal("100"))
        response = self.client.post(
            reverse("purchases:purchase_delete", args=[goal.pk])
        )
        self.assertRedirects(response, reverse("purchases:index"))
        self.assertFalse(PlannedPurchase.objects.exists())
        self.assertFalse(PurchaseContribution.objects.exists())

    def test_delete_goal_rejects_get(self):
        goal = self.make_goal()
        response = self.client.get(reverse("purchases:purchase_delete", args=[goal.pk]))
        self.assertEqual(response.status_code, 405)

    def test_delete_goal_unknown_is_404(self):
        response = self.client.post(
            reverse("purchases:purchase_delete", args=[999])
        )
        self.assertEqual(response.status_code, 404)

    # --- карточка цели ---

    def test_detail_shows_goal_and_contributions(self):
        goal = self.make_goal()
        PurchaseContribution.objects.create(
            purchase=goal, amount=Decimal("30000"), comment="Первая зарплата"
        )

        response = self.client.get(reverse("purchases:detail", args=[goal.pk]))
        self.assertContains(response, "Ноутбук")
        self.assertContains(response, "30\xa0000,00")
        self.assertContains(response, "60\xa0000,00")
        self.assertContains(response, "33 %")
        self.assertContains(response, "Первая зарплата")
        self.assertContains(response, "Итого взносов")
        self.assertEqual(response.context["contributions_total"], Decimal("30000.00"))

    def test_detail_empty_state(self):
        goal = self.make_goal()
        response = self.client.get(reverse("purchases:detail", args=[goal.pk]))
        self.assertContains(response, "Взносов ещё нет")

    def test_detail_unknown_is_404(self):
        response = self.client.get(reverse("purchases:detail", args=[999]))
        self.assertEqual(response.status_code, 404)

    def test_detail_shows_bought_date(self):
        goal = self.make_goal(
            status=PlannedPurchase.Status.BOUGHT,
            bought_at=date(2026, 5, 1),
        )
        response = self.client.get(reverse("purchases:detail", args=[goal.pk]))
        self.assertContains(response, "01.05.2026")

    # --- взносы ---

    def test_add_contribution(self):
        goal = self.make_goal()
        response = self.client.post(
            reverse("purchases:detail", args=[goal.pk]),
            {"date": "2026-09-10", "amount": "15000", "comment": "Аванс"},
        )
        self.assertRedirects(response, reverse("purchases:detail", args=[goal.pk]))
        contribution = PurchaseContribution.objects.get()
        self.assertEqual(contribution.purchase, goal)
        self.assertEqual(contribution.amount, Decimal("15000.00"))
        self.assertEqual(contribution.date, date(2026, 9, 10))
        self.assertEqual(contribution.comment, "Аванс")

    def test_contribution_form_defaults_to_today(self):
        goal = self.make_goal()
        response = self.client.get(reverse("purchases:detail", args=[goal.pk]))
        form = response.context["form"]
        # Модель даёт default=timezone.localdate — форма подставляет его.
        self.assertEqual(form["date"].value(), timezone.localdate())

    def test_add_contribution_rejects_non_positive_amount(self):
        goal = self.make_goal()
        for amount in ["0", "-5"]:
            with self.subTest(amount=amount):
                response = self.client.post(
                    reverse("purchases:detail", args=[goal.pk]),
                    {"date": "2026-09-10", "amount": amount, "comment": ""},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("amount", response.context["form"].errors)
        self.assertFalse(PurchaseContribution.objects.exists())

    def test_add_contribution_rejects_out_of_range_date(self):
        goal = self.make_goal()
        for value in ["1800-01-01", "2200-01-01"]:
            with self.subTest(value=value):
                response = self.client.post(
                    reverse("purchases:detail", args=[goal.pk]),
                    {"date": value, "amount": "100", "comment": ""},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("date", response.context["form"].errors)
        self.assertFalse(PurchaseContribution.objects.exists())

    def test_add_contribution_accepts_max_comment_length(self):
        goal = self.make_goal()
        response = self.client.post(
            reverse("purchases:detail", args=[goal.pk]),
            {"date": "2026-09-10", "amount": "100", "comment": "x" * 200},
        )
        self.assertRedirects(response, reverse("purchases:detail", args=[goal.pk]))

    def test_add_contribution_rejects_long_comment(self):
        goal = self.make_goal()
        response = self.client.post(
            reverse("purchases:detail", args=[goal.pk]),
            {"date": "2026-09-10", "amount": "100", "comment": "x" * 201},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PurchaseContribution.objects.exists())

    def test_add_contribution_rejects_missing_amount(self):
        goal = self.make_goal()
        response = self.client.post(
            reverse("purchases:detail", args=[goal.pk]),
            {"date": "2026-09-10", "amount": "", "comment": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PurchaseContribution.objects.exists())

    def test_update_contribution(self):
        goal = self.make_goal()
        contribution = PurchaseContribution.objects.create(
            purchase=goal, amount=Decimal("100"), date=date(2026, 9, 1)
        )
        response = self.post_json(
            reverse("purchases:contribution_update", args=[contribution.pk]),
            {"date": "2026-09-15", "amount": "250", "comment": "Больше"},
        )
        self.assertEqual(response.status_code, 200)
        contribution.refresh_from_db()
        self.assertEqual(contribution.amount, Decimal("250.00"))
        self.assertEqual(contribution.date, date(2026, 9, 15))
        self.assertEqual(contribution.comment, "Больше")

    def test_update_contribution_reports_field_error(self):
        goal = self.make_goal()
        contribution = PurchaseContribution.objects.create(
            purchase=goal, amount=Decimal("100")
        )
        response = self.post_json(
            reverse("purchases:contribution_update", args=[contribution.pk]),
            {"date": "2026-09-15", "amount": "0", "comment": ""},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["field"], "amount")

    def test_update_contribution_normalizes_scientific_amount(self):
        goal = self.make_goal()
        contribution = PurchaseContribution.objects.create(
            purchase=goal, amount=Decimal("100")
        )
        response = self.post_json(
            reverse("purchases:contribution_update", args=[contribution.pk]),
            {"date": "2026-09-15", "amount": "1e3", "comment": ""},
        )
        self.assertEqual(response.status_code, 200)
        contribution.refresh_from_db()
        self.assertEqual(contribution.amount, Decimal("1000.00"))

    def test_update_contribution_rejects_non_object_json(self):
        goal = self.make_goal()
        contribution = PurchaseContribution.objects.create(
            purchase=goal, amount=Decimal("100")
        )
        url = reverse("purchases:contribution_update", args=[contribution.pk])
        for body in ["null", json.dumps([1, 2])]:
            with self.subTest(body=body):
                response = self.client.post(
                    url, data=body, content_type="application/json"
                )
                self.assertEqual(response.status_code, 400)

    def test_update_contribution_rejects_get(self):
        goal = self.make_goal()
        contribution = PurchaseContribution.objects.create(
            purchase=goal, amount=Decimal("100")
        )
        response = self.client.get(
            reverse("purchases:contribution_update", args=[contribution.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_update_contribution_unknown_is_404(self):
        response = self.post_json(
            reverse("purchases:contribution_update", args=[999]),
            {"date": "2026-09-15", "amount": "100", "comment": ""},
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_contribution(self):
        goal = self.make_goal()
        contribution = PurchaseContribution.objects.create(
            purchase=goal, amount=Decimal("100")
        )
        response = self.client.post(
            reverse("purchases:contribution_delete", args=[contribution.pk])
        )
        self.assertRedirects(response, reverse("purchases:detail", args=[goal.pk]))
        self.assertFalse(PurchaseContribution.objects.exists())

    def test_delete_contribution_rejects_get(self):
        goal = self.make_goal()
        contribution = PurchaseContribution.objects.create(
            purchase=goal, amount=Decimal("100")
        )
        response = self.client.get(
            reverse("purchases:contribution_delete", args=[contribution.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_delete_contribution_unknown_is_404(self):
        response = self.client.post(
            reverse("purchases:contribution_delete", args=[999])
        )
        self.assertEqual(response.status_code, 404)

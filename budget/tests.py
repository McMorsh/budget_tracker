"""Тесты моделей бюджета."""
import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Allocation, BudgetMonth, Category
from .templatetags.money import rubles

class BudgetMonthTests(TestCase):
    def test_duplicate_month_is_rejected(self):
        BudgetMonth.objects.create(year=2026, month=10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BudgetMonth.objects.create(year=2026, month=10)

    def test_negative_income_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            BudgetMonth.objects.create(year=2026, month=10, income=Decimal("-1"))

    def test_title_contains_month_and_year(self):
        month = BudgetMonth(year=2026, month=10)
        self.assertIn("2026", month.title)
        self.assertIn("октяб", month.title.lower())

    def test_savings_amount(self):
        month = BudgetMonth(
            year=2026,
            month=10,
            income=Decimal("85000"),
            savings_percent=15,
        )
        self.assertEqual(month.savings_amount, Decimal("12750.00"))


class AllocationTests(TestCase):
    def setUp(self):
        self.month = BudgetMonth.objects.create(
            year=2026, month=10, income=Decimal("85000")
        )

    def test_amount_is_income_times_percent(self):
        category = Category.objects.create(name="Продукты")
        allocation = Allocation.objects.create(
            budget_month=self.month, category=category, percent=20
        )
        self.assertEqual(allocation.amount, Decimal("17000.00"))

    def test_amount_rounds_half_up(self):
        self.month.income = Decimal("10.05")
        category = Category.objects.create(name="Прочее")
        allocation = Allocation.objects.create(
            budget_month=self.month, category=category, percent=50
        )
        # 10,05 ₽ × 50 % = 5,025 → 5,03 (при банковском округлении было бы 5,02)
        self.assertEqual(allocation.amount, Decimal("5.03"))

    def test_percent_range_is_enforced(self):
        category = Category.objects.create(name="Прочее")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Allocation.objects.create(
                budget_month=self.month, category=category, percent=101
            )

    def test_planned_total_percent(self):
        for name, percent in [("Жильё", 35), ("Продукты", 20)]:
            Allocation.objects.create(
                budget_month=self.month,
                category=Category.objects.create(name=name),
                percent=percent,
            )
        self.month.savings_percent = 45
        self.assertEqual(self.month.planned_total_percent, 100)


class MoneyFilterTests(TestCase):
    def test_rubles_formats_with_grouping(self):
        self.assertEqual(rubles(Decimal("85000")), "85\xa0000 ₽")

    def test_rubles_with_two_decimals(self):
        self.assertEqual(rubles(Decimal("12750.5"), "2"), "12\xa0750,50 ₽")

    def test_rubles_rounds_half_up_by_default(self):
        # 5000,50 → 5 001 (половина вверх), как в budget.models.money
        self.assertEqual(rubles(Decimal("5000.50")), "5\xa0001 ₽")

    def test_rubles_handles_negative(self):
        self.assertEqual(rubles(Decimal("-7750")), "-7\xa0750 ₽")

    def test_rubles_handles_none_and_empty(self):
        self.assertEqual(rubles(None), "—")
        self.assertEqual(rubles(""), "—")

    def test_rubles_handles_garbage(self):
        self.assertEqual(rubles("abc"), "—")
        self.assertEqual(rubles(Decimal("1"), "x"), "—")


class CategoryViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )

    def setUp(self):
        self.client.force_login(self.user)

    def post_json(self, url, payload):
        return self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

    def test_section_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("budget:categories"))
        self.assertEqual(response.status_code, 302)

    def test_list_shows_active_and_archived(self):
        Category.objects.create(name="Продукты", position=1)
        Category.objects.create(name="Старое", position=2, is_active=False)

        response = self.client.get(reverse("budget:categories"))
        self.assertContains(response, "Продукты")
        self.assertContains(response, "Старое")
        self.assertContains(response, "Архив")
        self.assertContains(response, "drag-handle")
        self.assertContains(response, 'id="add-category"')

    def test_create_appends_to_the_end(self):
        Category.objects.create(name="Продукты", position=0)
        Category.objects.create(name="Транспорт", position=1)

        response = self.post_json(
            reverse("budget:category_create"), {"name": "Здоровье"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        new_category = Category.objects.get(name="Здоровье")
        self.assertEqual(new_category.position, 2)
        self.assertEqual(payload["id"], new_category.pk)
        self.assertIn(
            f"/budget/categories/{new_category.pk}/toggle/", payload["toggle_url"]
        )

    def test_create_first_category_gets_zero_position(self):
        self.post_json(reverse("budget:category_create"), {"name": "Здоровье"})

        new_category = Category.objects.get(name="Здоровье")
        self.assertEqual(new_category.position, 0)

    def test_create_rejects_duplicate_name(self):
        Category.objects.create(name="Продукты", position=1)

        response = self.post_json(
            reverse("budget:category_create"), {"name": "Продукты"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("уже существует", response.json()["error"])
        self.assertEqual(Category.objects.count(), 1)

    def test_create_rejects_empty_name(self):
        response = self.post_json(
            reverse("budget:category_create"), {"name": "   "}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Category.objects.count(), 0)

    def test_create_rejects_get(self):
        response = self.client.get(reverse("budget:category_create"))
        self.assertEqual(response.status_code, 405)

    def test_rename_changes_name_only(self):
        category = Category.objects.create(name="Продукты", position=3)

        response = self.post_json(
            reverse("budget:category_rename"),
            {"id": category.pk, "name": "Еда"},
        )

        self.assertEqual(response.status_code, 200)
        category.refresh_from_db()
        self.assertEqual(category.name, "Еда")
        self.assertEqual(category.position, 3)

    def test_rename_rejects_duplicate_name(self):
        Category.objects.create(name="Продукты", position=0)
        category = Category.objects.create(name="Транспорт", position=1)

        response = self.post_json(
            reverse("budget:category_rename"),
            {"id": category.pk, "name": "Продукты"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("уже существует", response.json()["error"])

    def test_rename_unknown_category(self):
        response = self.post_json(
            reverse("budget:category_rename"), {"id": 999, "name": "Еда"}
        )
        self.assertEqual(response.status_code, 404)

    def test_rename_rejects_bad_payload(self):
        response = self.post_json(reverse("budget:category_rename"), {"name": "Еда"})
        self.assertEqual(response.status_code, 400)

    def test_toggle_archives_and_restores(self):
        category = Category.objects.create(name="Продукты")

        self.client.post(reverse("budget:category_toggle", args=[category.pk]))
        category.refresh_from_db()
        self.assertFalse(category.is_active)

        self.client.post(reverse("budget:category_toggle", args=[category.pk]))
        category.refresh_from_db()
        self.assertTrue(category.is_active)

    def test_toggle_rejects_get(self):
        category = Category.objects.create(name="Продукты")
        response = self.client.get(
            reverse("budget:category_toggle", args=[category.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_reorder_updates_positions(self):
        first = Category.objects.create(name="Первая", position=0)
        second = Category.objects.create(name="Вторая", position=1)

        response = self.client.post(
            reverse("budget:category_reorder"),
            data=json.dumps({"ids": [second.pk, first.pk]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(second.position, 0)
        self.assertEqual(first.position, 1)

    def test_reorder_rejects_bad_payload(self):
        response = self.client.post(
            reverse("budget:category_reorder"),
            data="не json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_reorder_rejects_get(self):
        response = self.client.get(reverse("budget:category_reorder"))
        self.assertEqual(response.status_code, 405)

"""Тесты моделей бюджета."""
import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Allocation, BudgetMonth, Category
from .templatetags.money import rubles


class BudgetMonthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="owner", password="test-pass-123"
        )

    def test_duplicate_month_is_rejected(self):
        BudgetMonth.objects.create(owner=self.owner, year=2026, month=10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BudgetMonth.objects.create(owner=self.owner, year=2026, month=10)

    def test_negative_income_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            BudgetMonth.objects.create(
                owner=self.owner,
                year=2026,
                month=10,
                income=Decimal("-1"),
            )

    def test_title_contains_month_and_year(self):
        month = BudgetMonth(owner=self.owner, year=2026, month=10)
        self.assertIn("2026", month.title)
        self.assertIn("октяб", month.title.lower())

    def test_savings_amount(self):
        month = BudgetMonth(
            owner=self.owner,
            year=2026,
            month=10,
            income=Decimal("85000"),
            savings_percent=15,
        )
        self.assertEqual(month.savings_amount, Decimal("12750.00"))


class AllocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="owner", password="test-pass-123"
        )

    def setUp(self):
        self.month = BudgetMonth.objects.create(
            owner=self.owner,
            year=2026,
            month=10,
            income=Decimal("85000"),
        )

    def test_amount_is_income_times_percent(self):
        category = Category.objects.create(owner=self.owner, name="Продукты")
        allocation = Allocation.objects.create(
            budget_month=self.month, category=category, percent=20
        )
        self.assertEqual(allocation.amount, Decimal("17000.00"))

    def test_amount_rounds_half_up(self):
        self.month.income = Decimal("10.05")
        category = Category.objects.create(owner=self.owner, name="Прочее")
        allocation = Allocation.objects.create(
            budget_month=self.month, category=category, percent=50
        )
        # 10,05 ₽ × 50 % = 5,025 -> 5,03 (при банковском округлении было бы 5,02)
        self.assertEqual(allocation.amount, Decimal("5.03"))

    def test_percent_range_is_enforced(self):
        category = Category.objects.create(owner=self.owner, name="Прочее")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Allocation.objects.create(
                budget_month=self.month, category=category, percent=101
            )

    def test_planned_total_percent(self):
        for name, percent in [("Жильё", 35), ("Продукты", 20)]:
            Allocation.objects.create(
                budget_month=self.month,
                category=Category.objects.create(owner=self.owner, name=name),
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
        # 5000,50 -> 5 001 (половина вверх), как в budget.models.money
        self.assertEqual(rubles(Decimal("5000.50")), "5\xa0001 ₽")

    def test_rubles_handles_negative(self):
        self.assertEqual(rubles(Decimal("-7750")), "-7\xa0750 ₽")

    def test_rubles_handles_none_and_empty(self):
        self.assertEqual(rubles(None), "-")
        self.assertEqual(rubles(""), "-")

    def test_rubles_handles_garbage(self):
        self.assertEqual(rubles("abc"), "-")
        self.assertEqual(rubles(Decimal("1"), "x"), "-")


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
        Category.objects.create(owner=self.user, name="Продукты", position=1)
        Category.objects.create(
            owner=self.user, name="Старое", position=2, is_active=False
        )

        response = self.client.get(reverse("budget:categories"))
        self.assertContains(response, "Продукты")
        self.assertContains(response, "Старое")
        self.assertContains(response, "Архив")
        self.assertContains(response, "drag-handle")
        self.assertContains(response, 'id="add-category"')

    def test_create_appends_to_the_end(self):
        Category.objects.create(owner=self.user, name="Продукты", position=0)
        Category.objects.create(owner=self.user, name="Транспорт", position=1)

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
        Category.objects.create(owner=self.user, name="Продукты", position=1)

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
        category = Category.objects.create(
            owner=self.user, name="Продукты", position=3
        )

        response = self.post_json(
            reverse("budget:category_rename"),
            {"id": category.pk, "name": "Еда"},
        )

        self.assertEqual(response.status_code, 200)
        category.refresh_from_db()
        self.assertEqual(category.name, "Еда")
        self.assertEqual(category.position, 3)

    def test_rename_rejects_duplicate_name(self):
        Category.objects.create(owner=self.user, name="Продукты", position=0)
        category = Category.objects.create(
            owner=self.user, name="Транспорт", position=1
        )

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
        category = Category.objects.create(owner=self.user, name="Продукты")

        self.client.post(reverse("budget:category_toggle", args=[category.pk]))
        category.refresh_from_db()
        self.assertFalse(category.is_active)

        self.client.post(reverse("budget:category_toggle", args=[category.pk]))
        category.refresh_from_db()
        self.assertTrue(category.is_active)

    def test_toggle_rejects_get(self):
        category = Category.objects.create(owner=self.user, name="Продукты")
        response = self.client.get(
            reverse("budget:category_toggle", args=[category.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_reorder_updates_positions(self):
        first = Category.objects.create(owner=self.user, name="Первая", position=0)
        second = Category.objects.create(owner=self.user, name="Вторая", position=1)

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


class MonthPlanTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.category = Category.objects.create(
            owner=self.user, name="Продукты", position=0
        )

    def previous_month(self):
        year, month = self.today.year, self.today.month - 1
        if month < 1:
            year, month = year - 1, 12
        return year, month

    def test_index_renders_current_month(self):
        response = self.client.get(reverse("budget:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Доход")
        self.assertContains(response, "ещё не заполнен")
        self.assertContains(response, "Отложить")

    def test_month_url_requires_login(self):
        self.client.logout()
        response = self.client.get(
            reverse("budget:month", args=[self.today.year, self.today.month])
        )
        self.assertEqual(response.status_code, 302)

    def test_invalid_month_number_is_404(self):
        response = self.client.get(reverse("budget:month", args=[2026, 13]))
        self.assertEqual(response.status_code, 404)

    def test_out_of_range_year_is_404(self):
        # Крайние годы увели бы ссылки "назад/вперёд" за пределы дат Python - 500.
        for year, month in [(0, 1), (1899, 12), (2101, 1)]:
            with self.subTest(year=year):
                response = self.client.get(
                    reverse("budget:month", args=[year, month])
                )
                self.assertEqual(response.status_code, 404)

    def test_year_boundaries_render(self):
        for year, month in [(1900, 1), (2100, 12)]:
            with self.subTest(year=year):
                response = self.client.get(
                    reverse("budget:month", args=[year, month])
                )
                self.assertEqual(response.status_code, 200)

    def test_save_creates_month_and_allocations(self):
        response = self.client.post(
            reverse("budget:index"),
            {
                "income": "85000",
                "savings_percent": "15",
                f"percent_{self.category.pk}": "20",
            },
        )
        self.assertRedirects(response, reverse("budget:index"))

        month = BudgetMonth.objects.get(year=self.today.year, month=self.today.month)
        self.assertEqual(month.income, Decimal("85000"))
        self.assertEqual(month.savings_percent, 15)
        allocation = Allocation.objects.get(budget_month=month)
        self.assertEqual(allocation.category, self.category)
        self.assertEqual(allocation.percent, 20)

    def test_zero_percent_removes_allocation(self):
        month = BudgetMonth.objects.create(
            owner=self.user,
            year=self.today.year,
            month=self.today.month,
            income=Decimal("1000"),
        )
        Allocation.objects.create(
            budget_month=month, category=self.category, percent=20
        )

        self.client.post(
            reverse("budget:index"),
            {
                "income": "1000",
                "savings_percent": "0",
                f"percent_{self.category.pk}": "",
            },
        )

        self.assertFalse(Allocation.objects.exists())

    def test_percent_above_hundred_is_rejected(self):
        response = self.client.post(
            reverse("budget:index"),
            {
                "income": "1000",
                "savings_percent": "0",
                f"percent_{self.category.pk}": "150",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="errorlist"')
        self.assertFalse(BudgetMonth.objects.exists())

    def test_fractional_percent_is_rejected(self):
        response = self.client.post(
            reverse("budget:index"),
            {
                "income": "1000",
                "savings_percent": "0",
                f"percent_{self.category.pk}": "19.4",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="errorlist"')
        self.assertFalse(BudgetMonth.objects.exists())

    def test_unbalanced_plan_warns_but_saves(self):
        response = self.client.post(
            reverse("budget:index"),
            {
                "income": "10000",
                "savings_percent": "0",
                f"percent_{self.category.pk}": "50",
            },
            follow=True,
        )
        self.assertContains(response, "не хватает 50")
        self.assertTrue(BudgetMonth.objects.exists())

    def test_overspent_plan_warns_about_excess(self):
        response = self.client.post(
            reverse("budget:index"),
            {
                "income": "10000",
                "savings_percent": "20",
                f"percent_{self.category.pk}": "100",
            },
            follow=True,
        )
        self.assertContains(response, "перерасход")
        month = BudgetMonth.objects.get()
        self.assertEqual(month.planned_total_percent, 120)

    def test_balanced_plan_has_no_warning(self):
        response = self.client.post(
            reverse("budget:index"),
            {
                "income": "10000",
                "savings_percent": "20",
                f"percent_{self.category.pk}": "80",
            },
            follow=True,
        )
        self.assertContains(response, "План месяца сохранён")
        self.assertNotContains(response, "не хватает")

    def test_copy_from_previous_month(self):
        prev_year, prev_month = self.previous_month()
        source = BudgetMonth.objects.create(
            owner=self.user,
            year=prev_year,
            month=prev_month,
            income=Decimal("70000"),
            savings_percent=10,
        )
        Allocation.objects.create(
            budget_month=source, category=self.category, percent=25
        )
        # в текущем месяце уже есть свой план - он заменится
        target = BudgetMonth.objects.create(
            owner=self.user,
            year=self.today.year,
            month=self.today.month,
            income=Decimal("1"),
        )
        other = Category.objects.create(owner=self.user, name="Прочее", position=1)
        Allocation.objects.create(
            budget_month=target, category=other, percent=5
        )

        response = self.client.post(
            reverse("budget:month_copy", args=[self.today.year, self.today.month]),
            follow=True,
        )

        self.assertContains(response, "Скопировано из")
        target.refresh_from_db()
        self.assertEqual(target.income, Decimal("70000"))
        self.assertEqual(target.savings_percent, 10)
        allocations = Allocation.objects.filter(budget_month=target)
        self.assertEqual(allocations.count(), 1)
        allocation = allocations.get()
        self.assertEqual(allocation.category, self.category)
        self.assertEqual(allocation.percent, 25)

    def test_copy_without_previous_month_warns(self):
        response = self.client.post(
            reverse("budget:month_copy", args=[self.today.year, self.today.month]),
            follow=True,
        )
        self.assertContains(response, "копировать нечего")

    def test_archived_category_with_allocation_is_still_shown(self):
        month = BudgetMonth.objects.create(
            owner=self.user,
            year=self.today.year,
            month=self.today.month,
            income=Decimal("1000"),
        )
        archived = Category.objects.create(
            owner=self.user,
            name="Старое",
            position=1,
            is_active=False,
        )
        Allocation.objects.create(
            budget_month=month, category=archived, percent=10
        )

        response = self.client.get(reverse("budget:index"))
        self.assertContains(response, "Старое")
        self.assertContains(response, "(в архиве)")


class IsolationTests(TestCase):
    """Изоляция данных: второй пользователь не видит и не меняет чужое."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="owner", password="test-pass-123"
        )
        cls.other = User.objects.create_user(
            username="other", password="test-pass-123"
        )
        cls.today = timezone.localdate()

    def setUp(self):
        self.client.force_login(self.other)

    def post_json(self, url, payload):
        """Отправляет JSON-тело POST-запросом (как AJAX из интерфейса)."""
        return self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

    def test_category_list_hides_foreign_categories(self):
        """В списке категорий видны только свои категории."""
        Category.objects.create(owner=self.owner, name="Чужая")
        Category.objects.create(owner=self.other, name="Своя")

        response = self.client.get(reverse("budget:categories"))

        self.assertContains(response, "Своя")
        self.assertNotContains(response, "Чужая")

    def test_rename_foreign_category_is_not_found(self):
        """Чужую категорию переименовать нельзя, имя остаётся прежним."""
        category = Category.objects.create(owner=self.owner, name="Чужая")

        response = self.post_json(
            reverse("budget:category_rename"),
            {"id": category.pk, "name": "Взлом"},
        )

        self.assertEqual(response.status_code, 404)
        category.refresh_from_db()
        self.assertEqual(category.name, "Чужая")

    def test_toggle_foreign_category_is_not_found(self):
        """Чужую категорию нельзя отправить в архив."""
        category = Category.objects.create(owner=self.owner, name="Чужая")

        response = self.client.post(
            reverse("budget:category_toggle", args=[category.pk])
        )

        self.assertEqual(response.status_code, 404)
        category.refresh_from_db()
        self.assertTrue(category.is_active)

    def test_reorder_does_not_touch_foreign_positions(self):
        """Перетаскивание не меняет чужие позиции."""
        first = Category.objects.create(owner=self.owner, name="Первая", position=0)
        second = Category.objects.create(owner=self.owner, name="Вторая", position=1)

        response = self.client.post(
            reverse("budget:category_reorder"),
            data=json.dumps({"ids": [second.pk, first.pk]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.position, 0)
        self.assertEqual(second.position, 1)

    def test_month_screen_does_not_show_foreign_month(self):
        """Чужой заполненный месяц не виден на экране текущего месяца."""
        BudgetMonth.objects.create(
            owner=self.owner,
            year=self.today.year,
            month=self.today.month,
            income=Decimal("85000"),
        )

        response = self.client.get(reverse("budget:index"))

        self.assertIsNone(response.context["budget_month"])
        self.assertContains(response, "ещё не заполнен")

    def test_copy_does_not_use_foreign_month(self):
        """Чужой предыдущий месяц не годится как источник копирования."""
        year, month = self.today.year, self.today.month - 1
        if month < 1:
            year, month = year - 1, 12
        BudgetMonth.objects.create(
            owner=self.owner,
            year=year,
            month=month,
            income=Decimal("70000"),
        )

        response = self.client.post(
            reverse("budget:month_copy", args=[self.today.year, self.today.month]),
            follow=True,
        )

        self.assertContains(response, "копировать нечего")
        self.assertFalse(BudgetMonth.objects.filter(owner=self.other).exists())

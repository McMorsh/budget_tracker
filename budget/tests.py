"""Тесты моделей бюджета."""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

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

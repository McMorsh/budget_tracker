"""Тесты страницы входа, обзорной страницы и отчётов."""
import json
import re
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from budget.models import Allocation, BudgetMonth, Category
from expenses.models import Transaction
from purchases.models import PlannedPurchase, PurchaseContribution

from . import pdf as pdf_module


def chart_payload(response, element_id: str) -> dict:
    """Разбирает json_script-блок графика из ответа страницы."""
    html = response.content.decode()
    match = re.search(
        rf'<script id="{element_id}" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"на странице нет данных графика #{element_id}")
    return json.loads(match.group(1))


FOOTER_TEXT = "Budget Tracker - личный сайт учёта расходов"


class LoginRequiredTests(TestCase):
    """Неавторизованного пользователя middleware уводит на страницу входа."""

    def assert_redirected_to_login(self, response):
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(location.startswith(reverse("login")))
        self.assertIn("next=", location)

    def test_home_redirects_anonymous_to_login(self):
        self.assert_redirected_to_login(self.client.get(reverse("home")))

    def test_every_section_requires_login(self):
        for name in ["budget:index", "expenses:index", "purchases:index"]:
            with self.subTest(name=name):
                self.assert_redirected_to_login(self.client.get(reverse(name)))

    def test_reports_require_login(self):
        urls = [
            reverse("reports:index"),
            reverse("reports:month", args=[2026, 9]),
            reverse("reports:year", args=[2026]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assert_redirected_to_login(self.client.get(url))

    def test_admin_requires_login(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)



class LoginFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )

    def test_valid_credentials_redirect_to_home(self):
        response = self.client.post(
            reverse("login"),
            {"username": "owner", "password": "test-pass-123"},
        )
        self.assertRedirects(response, reverse("home"))

    def test_valid_credentials_respect_next(self):
        response = self.client.post(
            reverse("login") + "?next=" + reverse("budget:index"),
            {
                "username": "owner",
                "password": "test-pass-123",
                "next": reverse("budget:index"),
            },
        )
        self.assertRedirects(response, reverse("budget:index"))

    def test_invalid_credentials_show_error(self):
        response = self.client.post(
            reverse("login"),
            {"username": "owner", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert-error")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_rejects_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)

    def test_logout_redirects_to_login(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))


class FooterTests(TestCase):
    """Подпись сайта есть на каждой странице - общий каркас base.html."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )

    def test_footer_is_on_every_page(self):
        self.client.force_login(self.user)
        urls = [
            reverse("home"),
            reverse("budget:index"),
            reverse("budget:categories"),
            reverse("expenses:index"),
            reverse("reports:index"),
            reverse("purchases:index"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, FOOTER_TEXT)

        # Страница входа доступна анонимно; при входе её перекинуло бы на главную.
        self.client.logout()
        response = self.client.get(reverse("login"))
        self.assertContains(response, FOOTER_TEXT)


class HomeViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_home_renders_without_data(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Обзор")
        self.assertContains(response, "ещё не заполнен")

    def test_home_shows_month_summary(self):
        today = timezone.localdate()
        BudgetMonth.objects.create(
            year=today.year,
            month=today.month,
            income=Decimal("85000"),
            savings_percent=Decimal("15"),
            owner=self.user,
        )
        category = Category.objects.create(name="Продукты", owner=self.user)
        Transaction.objects.create(
            category=category, amount=Decimal("5000"), date=today, owner=self.user
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "85\xa0000")  # доход
        self.assertContains(response, "12\xa0750")  # "отложить" (15 %)
        self.assertContains(response, "5\xa0000")  # потрачено
        self.assertContains(response, "67\xa0250")  # свободно от дохода
        self.assertContains(response, "15 % из 100 %")  # заполненность плана

    def test_home_marks_negative_free_amount(self):
        today = timezone.localdate()
        BudgetMonth.objects.create(
            year=today.year,
            month=today.month,
            income=Decimal("10000"),
            savings_percent=Decimal("0"),
            owner=self.user,
        )
        category = Category.objects.create(name="Продукты", owner=self.user)
        Transaction.objects.create(
            category=category, amount=Decimal("12000"), date=today, owner=self.user
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, 'class="negative"')
        self.assertContains(response, "-2\xa0000")

    def test_home_shows_active_goals(self):
        purchase = PlannedPurchase.objects.create(
            title="Ноутбук",
            amount=Decimal("90000"),
            status=PlannedPurchase.Status.SAVING,
            owner=self.user,
        )
        PurchaseContribution.objects.create(
            purchase=purchase, amount=Decimal("15000")
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Ноутбук")
        self.assertContains(response, "75\xa0000")  # осталось накопить

    def test_home_orders_goals_by_priority(self):
        PlannedPurchase.objects.create(
            title="Низкий",
            amount=Decimal("1000"),
            priority=0,
            status=PlannedPurchase.Status.SAVING,
            owner=self.user,
        )
        PlannedPurchase.objects.create(
            title="Высокий",
            amount=Decimal("1000"),
            priority=5,
            status=PlannedPurchase.Status.SAVING,
            owner=self.user,
        )

        content = self.client.get(reverse("home")).content.decode()
        self.assertLess(content.index("Высокий"), content.index("Низкий"))

    def test_home_links_to_reports(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, reverse("reports:index"))


class MonthReportTests(TestCase):
    """Отчёт "план/факт" за месяц."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )
        cls.category = Category.objects.create(
            name="Продукты", position=0, owner=cls.user
        )

    def setUp(self):
        self.client.force_login(self.user)

    def month_url(self, year: int = 2026, month: int = 9) -> str:
        return reverse("reports:month", args=[year, month])

    def make_month(
        self, year: int = 2026, month: int = 9, income: str = "85000", percent: int = 40
    ) -> BudgetMonth:
        budget_month = BudgetMonth.objects.create(
            year=year,
            month=month,
            income=Decimal(income),
            savings_percent=15,
            owner=self.user,
        )
        Allocation.objects.create(
            budget_month=budget_month, category=self.category, percent=percent
        )
        return budget_month

    def test_month_report_shows_summary_and_rows(self):
        self.make_month()
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("1000"),
            date=date(2026, 9, 5),
            owner=self.user,
        )
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("500"),
            date=date(2026, 9, 6),
            owner=self.user,
        )

        response = self.client.get(self.month_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Отчёт")
        self.assertContains(response, "85\xa0000")  # доход
        self.assertContains(response, "12\xa0750")  # "отложить": 15 %
        self.assertContains(response, "34\xa0000")  # бюджет: 85 000 × 40 %
        self.assertContains(response, "1\xa0500")  # траты
        # Столбцы отчёта: "Бюджет / Траты / Остаток".
        self.assertContains(response, "Бюджет, ₽")
        self.assertContains(response, "Траты, ₽")
        self.assertContains(response, "Остаток, ₽")
        # Остаток: 34 000 - 1 500; бюджет не израсходован - "+" и зелёный.
        self.assertContains(response, "+32\xa0500,00")
        self.assertContains(response, 'class="num positive"')

    def test_month_report_shows_used_percent_and_overspend(self):
        self.make_month(percent=1)  # план 850 ₽
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("900"),
            date=date(2026, 9, 5),
            owner=self.user,
        )

        response = self.client.get(self.month_url())
        self.assertContains(response, "106 %")  # 900 / 850 × 100 = 105.9 -> 106
        # Перерасход: остаток отрицательный - минус и красный.
        self.assertContains(response, "-50,00")
        self.assertContains(response, 'class="num negative"')
        self.assertContains(response, 'class="progress over"')

    def test_month_report_includes_category_with_fact_but_no_plan(self):
        self.make_month()
        extra = Category.objects.create(name="Такси", position=1, owner=self.user)
        Transaction.objects.create(
            category=extra,
            amount=Decimal("300"),
            date=date(2026, 9, 7),
            owner=self.user,
        )

        response = self.client.get(self.month_url())
        self.assertContains(response, "Такси")
        self.assertContains(response, "300,00")

    def test_month_report_includes_archived_category(self):
        self.make_month()
        archived = Category.objects.create(
            name="Старое", position=2, is_active=False, owner=self.user
        )
        Transaction.objects.create(
            category=archived,
            amount=Decimal("200"),
            date=date(2026, 9, 8),
            owner=self.user,
        )

        response = self.client.get(self.month_url())
        self.assertContains(response, "Старое")
        self.assertContains(response, "(в архиве)")

    def test_month_report_empty(self):
        response = self.client.get(self.month_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "нет ни бюджета, ни трат")

    def test_month_report_without_budget_month(self):
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("700"),
            date=date(2026, 9, 5),
            owner=self.user,
        )

        response = self.client.get(self.month_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "700,00")
        self.assertContains(response, '<td class="num">0,00 ₽</td>')  # плана нет
        # Без плана всё потраченное - перерасход: минус и красный.
        self.assertContains(response, 'class="num negative"')
        # Без дохода "свободно от дохода" не считаем - прочерк, а не минус.
        self.assertContains(response, "<dd>-</dd>")

    def test_month_report_links_to_year_with_month(self):
        response = self.client.get(self.month_url(2026, 9))
        self.assertContains(
            response, reverse("reports:year", args=[2026]) + "?month=9"
        )

    def test_month_report_has_pdf_link(self):
        response = self.client.get(self.month_url())
        self.assertContains(response, reverse("reports:pdf", args=[2026, 9]))

    def test_month_report_invalid_month_is_404(self):
        for month in [0, 13]:
            with self.subTest(month=month):
                response = self.client.get(
                    reverse("reports:month", args=[2026, month])
                )
                self.assertEqual(response.status_code, 404)

    def test_month_report_out_of_range_year_is_404(self):
        for year, month in [(0, 1), (1899, 12), (2101, 1), (10000, 1)]:
            with self.subTest(year=year):
                response = self.client.get(
                    reverse("reports:month", args=[year, month])
                )
                self.assertEqual(response.status_code, 404)

    def test_month_report_boundaries_render(self):
        for year, month in [(1900, 1), (2100, 12)]:
            with self.subTest(year=year):
                response = self.client.get(
                    reverse("reports:month", args=[year, month])
                )
                self.assertEqual(response.status_code, 200)

    def test_month_report_hides_arrows_on_boundaries(self):
        response = self.client.get(reverse("reports:month", args=[1900, 1]))
        self.assertNotContains(response, reverse("reports:month", args=[1899, 12]))
        response = self.client.get(reverse("reports:month", args=[2100, 12]))
        self.assertNotContains(response, reverse("reports:month", args=[2101, 1]))

    def test_category_rows_follow_position_order(self):
        # pk, имя и position расходятся: порядок должен быть по position.
        apples = Category.objects.create(name="Яблоки", position=2, owner=self.user)
        bananas = Category.objects.create(name="Бананы", position=1, owner=self.user)
        for category in (self.category, apples, bananas):
            Transaction.objects.create(
                category=category,
                amount=Decimal("100"),
                date=date(2026, 9, 5),
                owner=self.user,
            )

        response = self.client.get(self.month_url())
        html = response.content.decode()
        self.assertLess(html.index("Продукты"), html.index("Бананы"))
        self.assertLess(html.index("Бананы"), html.index("Яблоки"))

    def test_planned_amount_rounds_half_up(self):
        self.make_month(income="1.25", percent=10)  # 0,125 -> 0,13
        response = self.client.get(self.month_url())
        self.assertContains(response, "0,13")

    def test_zero_income_plan_is_not_counted(self):
        self.make_month(income="0", percent=50)
        response = self.client.get(self.month_url())
        # Процент исполнения - прочерк в ячейке, а не ноль.
        self.assertRegex(response.content.decode(), r"-\s*</td>")
        self.assertNotContains(response, "plan-progress")

    def test_used_percent_at_plan_has_no_over_class(self):
        self.make_month(percent=85)  # Σ = 100 %, план 72 250 ₽
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("72250"),
            date=date(2026, 9, 5),
            owner=self.user,
        )
        response = self.client.get(self.month_url())
        self.assertRegex(response.content.decode(), r"100 %\s*</span>")
        self.assertNotContains(response, 'class="progress over"')
        # План израсходован ровно - разница без знака и без класса.
        self.assertContains(response, '<td class="num">0,00 ₽</td>')

    def test_progress_bar_is_clamped_for_overspend(self):
        self.make_month(percent=10)  # план 8 500 ₽
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("17000"),
            date=date(2026, 9, 5),
            owner=self.user,
        )
        response = self.client.get(self.month_url())
        self.assertContains(response, "200 %")
        self.assertContains(response, 'style="width: 100%"')
        self.assertContains(response, 'class="progress over"')

    def test_month_report_warns_about_incomplete_plan(self):
        self.make_month(percent=40)  # Σ = 40 + 15 = 55 %
        response = self.client.get(self.month_url())
        self.assertContains(response, "Σ долей = 55 % из 100 %")

    def test_month_report_has_no_warning_when_plan_is_complete(self):
        self.make_month(percent=85)  # Σ = 85 + 15 = 100 %
        response = self.client.get(self.month_url())
        self.assertNotContains(response, "Σ долей")

    def test_index_opens_current_month_and_links_to_year(self):
        today = timezone.localdate()
        response = self.client.get(reverse("reports:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Итоги {today.year} года")
        self.assertContains(response, reverse("reports:year", args=[today.year]))

    def test_month_report_chart_data(self):
        self.make_month()
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("1000"),
            date=date(2026, 9, 5),
            owner=self.user,
        )

        response = self.client.get(self.month_url())
        payload = chart_payload(response, "plan-fact-data")
        self.assertEqual(payload["labels"], ["Продукты"])
        self.assertEqual(payload["planned"], [34000.0])
        self.assertEqual(payload["fact"], [1000.0])


class YearReportTests(TestCase):
    """Итоги года."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )
        cls.category = Category.objects.create(
            name="Продукты", position=0, owner=cls.user
        )

    def setUp(self):
        self.client.force_login(self.user)

    def year_url(self, year: int = 2026) -> str:
        return reverse("reports:year", args=[year])

    def make_month(
        self, month: int, income: str, percent: int, day: int, fact: str
    ) -> BudgetMonth:
        budget_month = BudgetMonth.objects.create(
            year=2026,
            month=month,
            income=Decimal(income),
            savings_percent=10,
            owner=self.user,
        )
        Allocation.objects.create(
            budget_month=budget_month, category=self.category, percent=percent
        )
        Transaction.objects.create(
            category=self.category,
            amount=Decimal(fact),
            date=date(2026, month, day),
            owner=self.user,
        )
        return budget_month

    def test_year_report_totals_and_months(self):
        self.make_month(month=1, income="80000", percent=40, day=5, fact="1000")
        self.make_month(month=2, income="90000", percent=20, day=6, fact="2000")

        response = self.client.get(self.year_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Итоги 2026 года")
        self.assertContains(response, "Январь")
        self.assertContains(response, "Февраль")
        self.assertContains(response, "170\xa0000")  # доход за год
        self.assertContains(response, "50\xa0000")  # бюджет: 32 000 + 18 000
        self.assertContains(response, "3\xa0000")  # траты: 1 000 + 2 000

    def test_year_report_links_to_months(self):
        BudgetMonth.objects.create(
            year=2026,
            month=3,
            income=Decimal("10000"),
            savings_percent=0,
            owner=self.user,
        )
        response = self.client.get(self.year_url())
        self.assertContains(response, reverse("reports:month", args=[2026, 3]))

    def test_year_report_has_pdf_link(self):
        response = self.client.get(self.year_url())
        self.assertContains(response, reverse("reports:pdf_year", args=[2026]))

    def test_year_report_back_link_returns_to_origin_month(self):
        response = self.client.get(self.year_url() + "?month=5")
        self.assertContains(response, "К месячному отчёту")
        self.assertContains(response, reverse("reports:month", args=[2026, 5]))

    def test_year_report_back_link_defaults_to_current_month(self):
        today = timezone.localdate()
        response = self.client.get(reverse("reports:year", args=[today.year]))
        self.assertContains(
            response, reverse("reports:month", args=[today.year, today.month])
        )

    def test_year_report_back_link_defaults_to_last_month_with_data(self):
        # Для прошлого года возвращаемся в последний месяц с данными.
        BudgetMonth.objects.create(
            year=2025,
            month=4,
            income=Decimal("10000"),
            savings_percent=0,
            owner=self.user,
        )
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("100"),
            date=date(2025, 4, 5),
            owner=self.user,
        )
        response = self.client.get(reverse("reports:year", args=[2025]))
        url = reverse("reports:month", args=[2025, 4])
        self.assertContains(response, f'href="{url}">← К месячному отчёту</a>')

    def test_year_report_back_link_ignores_invalid_month(self):
        today = timezone.localdate()
        url = reverse("reports:month", args=[today.year, today.month])
        for raw in ["0", "13", "abc", "²"]:
            with self.subTest(month=raw):
                response = self.client.get(
                    reverse("reports:year", args=[today.year]) + f"?month={raw}"
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response, f'href="{url}">← К месячному отчёту</a>'
                )

    def test_year_report_marks_positive_and_negative_differences(self):
        # Январь: бюджет 20 000, траты 10 000 -> "+10 000" зелёным.
        # Февраль: бюджет 20 000, траты 30 000 -> "-10 000" красным.
        self.make_month(month=1, income="20000", percent=100, day=5, fact="10000")
        self.make_month(month=2, income="20000", percent=100, day=6, fact="30000")

        response = self.client.get(self.year_url())
        html = response.content.decode()
        self.assertIn("+10\xa0000", html)
        self.assertIn("-10\xa0000", html)
        self.assertIn('class="num positive"', html)
        self.assertIn('class="num negative"', html)

    def test_year_report_zero_difference_has_no_sign(self):
        self.make_month(month=1, income="1000", percent=100, day=5, fact="1000")
        response = self.client.get(self.year_url())
        self.assertContains(response, '<td class="num">0,00 ₽</td>')

    def test_year_report_category_with_plan_only(self):
        budget_month = BudgetMonth.objects.create(
            year=2026,
            month=1,
            income=Decimal("10000"),
            savings_percent=0,
            owner=self.user,
        )
        Allocation.objects.create(
            budget_month=budget_month, category=self.category, percent=50
        )
        response = self.client.get(self.year_url())
        self.assertContains(response, "5\xa0000,00")  # бюджет
        self.assertRegex(response.content.decode(), r"0 %\s*</span>")

    def test_year_report_months_without_budget(self):
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("500"),
            date=date(2026, 5, 5),
            owner=self.user,
        )
        response = self.client.get(self.year_url())
        self.assertContains(response, "Май")
        self.assertContains(response, "500,00")

    def test_year_report_month_without_rows_shows_empty_state(self):
        BudgetMonth.objects.create(
            year=2026,
            month=1,
            income=Decimal("10000"),
            savings_percent=0,
            owner=self.user,
        )
        response = self.client.get(self.year_url())
        self.assertContains(response, "Бюджета и трат по категориям за год нет.")

    def test_year_report_empty(self):
        response = self.client.get(self.year_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "данных пока нет")

    def test_year_out_of_range_is_404(self):
        for year in [1899, 2101]:
            with self.subTest(year=year):
                response = self.client.get(reverse("reports:year", args=[year]))
                self.assertEqual(response.status_code, 404)

    def test_year_boundaries_render(self):
        for year in [1900, 2100]:
            with self.subTest(year=year):
                response = self.client.get(reverse("reports:year", args=[year]))
                self.assertEqual(response.status_code, 200)

    def test_year_report_charts(self):
        self.make_month(month=1, income="80000", percent=40, day=5, fact="1000")
        extra = Category.objects.create(name="Такси", position=1, owner=self.user)
        Transaction.objects.create(
            category=extra,
            amount=Decimal("300"),
            date=date(2026, 2, 7),
            owner=self.user,
        )

        response = self.client.get(self.year_url())
        months = chart_payload(response, "year-months-data")
        self.assertEqual(months["labels"], ["Январь", "Февраль"])
        self.assertEqual(months["planned"], [32000.0, 0.0])
        self.assertEqual(months["fact"], [1000.0, 300.0])

        structure = chart_payload(response, "year-structure-data")
        self.assertEqual(structure["labels"], ["Продукты", "Такси"])
        self.assertEqual(structure["fact"], [1000.0, 300.0])


class PdfMediaMixin(TestCase):
    """Общая часть PDF-тестов: вход и временный MEDIA_ROOT."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )
        cls.category = Category.objects.create(
            name="Продукты", position=0, owner=cls.user
        )

    def setUp(self):
        self.client.force_login(self.user)
        # PDF собирается по-настоящему (WeasyPrint + matplotlib), но в
        # временный MEDIA_ROOT, чтобы не мусорить в media проекта.
        self.media = tempfile.mkdtemp(prefix="bt-media-")
        settings_override = override_settings(MEDIA_ROOT=self.media)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.addCleanup(shutil.rmtree, self.media, True)


class MonthReportPdfTests(PdfMediaMixin):
    """PDF-отчёт за месяц."""

    def pdf_url(self, year: int = 2026, month: int = 9) -> str:
        return reverse("reports:pdf", args=[year, month])

    def test_pdf_requires_login(self):
        self.client.logout()
        response = self.client.get(self.pdf_url())
        self.assertEqual(response.status_code, 302)

    def test_pdf_out_of_range_is_404(self):
        for year, month in [(1800, 1), (2026, 0), (2026, 13)]:
            with self.subTest(year=year, month=month):
                response = self.client.get(
                    reverse("reports:pdf", args=[year, month])
                )
                self.assertEqual(response.status_code, 404)

    def test_pdf_generates_file_and_downloads(self):
        budget_month = BudgetMonth.objects.create(
            year=2026,
            month=9,
            income=Decimal("85000"),
            savings_percent=15,
            owner=self.user,
        )
        Allocation.objects.create(
            budget_month=budget_month, category=self.category, percent=40
        )
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("1000"),
            date=date(2026, 9, 5),
            owner=self.user,
        )

        response = self.client.get(self.pdf_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])

        content = b"".join(getattr(response, "streaming_content"))
        self.assertTrue(content.startswith(b"%PDF-"))

        path = Path(self.media) / "reports" / str(self.user.pk) / "2026-09.pdf"
        self.assertTrue(path.exists())
        self.assertTrue(path.read_bytes().startswith(b"%PDF-"))

    def test_pdf_for_month_without_data(self):
        # Месяц без бюджета и трат: графиков нет, но PDF собирается.
        response = self.client.get(self.pdf_url())
        self.assertEqual(response.status_code, 200)
        path = Path(self.media) / "reports" / str(self.user.pk) / "2026-09.pdf"
        self.assertTrue(path.exists())
        self.assertTrue(path.read_bytes().startswith(b"%PDF-"))

    def test_pdf_repeat_download_overwrites_file(self):
        self.client.get(self.pdf_url())
        path = Path(self.media) / "reports" / str(self.user.pk) / "2026-09.pdf"
        self.assertTrue(path.read_bytes().startswith(b"%PDF-"))

        response = self.client.get(self.pdf_url())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
        # Атомарная запись не оставляет временных файлов.
        self.assertFalse(path.with_suffix(".pdf.part").exists())

    def test_pdf_content_disposition(self):
        response = self.client.get(self.pdf_url())
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="budget-report-2026-09.pdf"',
        )

    def test_pdf_without_dependencies_shows_hint(self):
        # Образ, собранный без WeasyPrint/matplotlib: 500 не нужен - даём подсказку.
        with mock.patch.object(
            pdf_module, "build_report_pdf", side_effect=ImportError("No matplotlib")
        ):
            response = self.client.get(self.pdf_url(), follow=True)
        self.assertRedirects(response, reverse("reports:month", args=[2026, 9]))
        self.assertContains(response, "Пересоберите образ")

    def test_pdf_helpers(self):
        self.assertEqual(
            pdf_module.report_path(self.user, 2026, 9),
            Path(self.media) / "reports" / str(self.user.pk) / "2026-09.pdf",
        )
        self.assertEqual(
            pdf_module.report_path(self.user, 2026),
            Path(self.media) / "reports" / str(self.user.pk) / "2026.pdf",
        )
        self.assertEqual(pdf_module._thousands(34000.0), "34\xa0000")
        self.assertEqual(pdf_module._percent_label(3.5), "")
        self.assertEqual(pdf_module._percent_label(12.0), "12%")
        self.assertTrue(
            pdf_module._png_data_uri(b"png").startswith("data:image/png;base64,")
        )


class YearReportPdfTests(PdfMediaMixin):
    """PDF-отчёт за год."""

    def pdf_url(self, year: int = 2026) -> str:
        return reverse("reports:pdf_year", args=[year])

    def test_pdf_requires_login(self):
        self.client.logout()
        response = self.client.get(self.pdf_url())
        self.assertEqual(response.status_code, 302)

    def test_pdf_out_of_range_is_404(self):
        for year in [1899, 2101]:
            with self.subTest(year=year):
                response = self.client.get(reverse("reports:pdf_year", args=[year]))
                self.assertEqual(response.status_code, 404)

    def test_pdf_generates_file_and_downloads(self):
        budget_month = BudgetMonth.objects.create(
            year=2026,
            month=1,
            income=Decimal("80000"),
            savings_percent=10,
            owner=self.user,
        )
        Allocation.objects.create(
            budget_month=budget_month, category=self.category, percent=40
        )
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("1000"),
            date=date(2026, 1, 5),
            owner=self.user,
        )

        response = self.client.get(self.pdf_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="budget-report-2026.pdf"',
        )

        content = b"".join(getattr(response, "streaming_content"))
        self.assertTrue(content.startswith(b"%PDF-"))

        path = Path(self.media) / "reports" / str(self.user.pk) / "2026.pdf"
        self.assertTrue(path.read_bytes().startswith(b"%PDF-"))

    def test_pdf_for_year_without_data(self):
        # Год без данных: графиков нет, но PDF собирается.
        response = self.client.get(self.pdf_url())
        self.assertEqual(response.status_code, 200)
        path = Path(self.media) / "reports" / str(self.user.pk) / "2026.pdf"
        self.assertTrue(path.read_bytes().startswith(b"%PDF-"))

    def test_pdf_for_year_with_expenses_without_budget(self):
        # Траты без бюджетных месяцев: таблица месяцев есть, бюджета нет.
        Transaction.objects.create(
            category=self.category,
            amount=Decimal("500"),
            date=date(2026, 5, 5),
            owner=self.user,
        )
        response = self.client.get(self.pdf_url())
        self.assertEqual(response.status_code, 200)
        path = Path(self.media) / "reports" / str(self.user.pk) / "2026.pdf"
        self.assertTrue(path.read_bytes().startswith(b"%PDF-"))

    def test_pdf_repeat_download_leaves_no_temp_files(self):
        self.client.get(self.pdf_url())
        response = self.client.get(self.pdf_url())
        self.assertEqual(response.status_code, 200)
        report_dir = Path(self.media) / "reports" / str(self.user.pk)
        self.assertEqual(
            sorted(item.name for item in report_dir.iterdir()), ["2026.pdf"]
        )

    def test_pdf_without_dependencies_shows_hint(self):
        with mock.patch.object(
            pdf_module, "build_year_pdf", side_effect=ImportError("No matplotlib")
        ):
            response = self.client.get(self.pdf_url(), follow=True)
        self.assertRedirects(response, reverse("reports:year", args=[2026]))
        self.assertContains(response, "Пересоберите образ")


class ReportIsolationTests(TestCase):
    """Изоляция данных в отчётах: владельцы не видят чужие суммы."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )
        cls.other = User.objects.create_user(
            username="other", password="test-pass-123"
        )
        cls.category = Category.objects.create(
            name="Продукты", position=0, owner=cls.user
        )
        # Свои данные: доход 50 000, бюджет 25 000, трата 1 234.
        own_budget = BudgetMonth.objects.create(
            year=2026,
            month=9,
            income=Decimal("50000"),
            savings_percent=10,
            owner=cls.user,
        )
        Allocation.objects.create(
            budget_month=own_budget, category=cls.category, percent=50
        )
        Transaction.objects.create(
            owner=cls.user,
            category=cls.category,
            amount=Decimal("1234"),
            date=date(2026, 9, 5),
        )
        # Данные второго владельца: ни суммы, ни категория не должны
        # попадать в отчёты первого - ни за тот же месяц, ни за год.
        other_budget = BudgetMonth.objects.create(
            year=2026,
            month=9,
            income=Decimal("999999"),
            savings_percent=0,
            owner=cls.other,
        )
        other_category = Category.objects.create(
            name="Чужие траты", position=0, owner=cls.other
        )
        Allocation.objects.create(
            budget_month=other_budget, category=other_category, percent=100
        )
        Transaction.objects.create(
            owner=cls.other,
            category=other_category,
            amount=Decimal("777777"),
            date=date(2026, 9, 6),
        )
        # Месяц, который есть только у второго владельца: в годовой таблице
        # первого его быть не должно.
        BudgetMonth.objects.create(
            year=2026,
            month=4,
            income=Decimal("888888"),
            savings_percent=0,
            owner=cls.other,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_month_report_does_not_mix_owners(self):
        """Проверяет, что месячный отчёт не смешивает данные владельцев."""
        response = self.client.get(reverse("reports:month", args=[2026, 9]))
        self.assertContains(response, "50\xa0000")  # свой доход
        self.assertContains(response, "1\xa0234")  # своя трата
        self.assertNotContains(response, "999\xa0999")
        self.assertNotContains(response, "777\xa0777")
        self.assertNotContains(response, "Чужие траты")

    def test_year_report_does_not_mix_owners(self):
        """Проверяет, что годовой отчёт не смешивает данные владельцев."""
        response = self.client.get(reverse("reports:year", args=[2026]))
        self.assertContains(response, "Сентябрь")
        self.assertContains(response, "1\xa0234")  # своя трата
        self.assertNotContains(response, "Апрель")
        self.assertNotContains(response, "999\xa0999")
        self.assertNotContains(response, "777\xa0777")
        self.assertNotContains(response, "Чужие траты")

    def test_home_does_not_show_foreign_data(self):
        """Проверяет, что обзор текущего месяца не смешивает владельцев."""
        today = timezone.localdate()
        BudgetMonth.objects.create(
            year=today.year,
            month=today.month,
            income=Decimal("50000"),
            savings_percent=0,
            owner=self.user,
        )
        BudgetMonth.objects.create(
            year=today.year,
            month=today.month,
            income=Decimal("123000"),
            savings_percent=0,
            owner=self.other,
        )
        Transaction.objects.create(
            owner=self.other,
            category=Category.objects.get(name="Чужие траты", owner=self.other),
            amount=Decimal("777777"),
            date=today,
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "50\xa0000")  # свой доход
        self.assertNotContains(response, "123\xa0000")
        self.assertNotContains(response, "777\xa0777")

    def test_pdf_paths_differ_per_owner(self):
        """Проверяет, что PDF владельцев лежат в разных подкаталогах media."""
        own = pdf_module.report_path(self.user, 2026, 9)
        other = pdf_module.report_path(self.other, 2026, 9)
        self.assertNotEqual(own, other)
        self.assertEqual(own.parent.name, str(self.user.pk))
        self.assertEqual(other.parent.name, str(self.other.pk))
        self.assertNotEqual(
            pdf_module.report_path(self.user, 2026),
            pdf_module.report_path(self.other, 2026),
        )

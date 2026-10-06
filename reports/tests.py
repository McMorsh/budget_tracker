"""Тесты страницы входа, обзорной страницы и закрытия сайта входом."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from budget.models import BudgetMonth, Category
from expenses.models import Transaction
from purchases.models import PlannedPurchase, PurchaseContribution


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
        for name in ["budget:index", "expenses", "purchases"]:
            with self.subTest(name=name):
                self.assert_redirected_to_login(self.client.get(reverse(name)))

    def test_admin_requires_login(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)

    def test_login_page_is_public(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "только для владельца")


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
        )
        category = Category.objects.create(name="Продукты")
        Transaction.objects.create(
            category=category, amount=Decimal("5000"), date=today
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "85\xa0000")  # доход
        self.assertContains(response, "12\xa0750")  # «отложить» (15 %)
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
        )
        category = Category.objects.create(name="Продукты")
        Transaction.objects.create(
            category=category, amount=Decimal("12000"), date=today
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, 'class="negative"')
        self.assertContains(response, "-2\xa0000")

    def test_home_shows_active_goals(self):
        purchase = PlannedPurchase.objects.create(
            title="Ноутбук",
            amount=Decimal("90000"),
            status=PlannedPurchase.Status.SAVING,
        )
        PurchaseContribution.objects.create(
            purchase=purchase, amount=Decimal("15000")
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Ноутбук")
        self.assertContains(response, "75\xa0000")  # осталось накопить


class ComingSoonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="owner", password="test-pass-123"
        )

    def test_section_pages_show_placeholder(self):
        self.client.force_login(self.user)
        for name, phase in (("expenses", 5), ("purchases", 8)):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, "Раздел в разработке")
                self.assertContains(response, f"Фазе {phase}")

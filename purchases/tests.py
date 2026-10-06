"""Тесты моделей планов покупок."""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import PlannedPurchase, PurchaseContribution


class PlannedPurchaseTests(TestCase):
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

    def test_non_positive_contribution_is_rejected(self):
        purchase = PlannedPurchase.objects.create(
            title="Наушники", amount=Decimal("12000")
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseContribution.objects.create(purchase=purchase, amount=Decimal("0"))

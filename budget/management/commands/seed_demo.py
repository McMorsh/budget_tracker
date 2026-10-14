"""Демо-данные для локальной разработки.

Данные синтетические: из живой базы ничего не берётся и не публикуется.
Команда предназначена для разработки; при DEBUG=False откажется работать
без явного --force. Данные принадлежат одному пользователю (по умолчанию -
первому суперпользователю; свой логин - через --user).

Примеры:
    python manage.py seed_demo              # 3 месяца демо-данных
    python manage.py seed_demo --user owner
    python manage.py seed_demo --months 6
    python manage.py seed_demo --reset      # удалить старые данные и создать заново
"""
import random
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from budget.models import Allocation, BudgetMonth, Category
from budget.utils import shift_month
from expenses.models import Transaction
from purchases.models import PlannedPurchase, PurchaseContribution

# Категории и плановая доля от дохода, %.
# Σ (85 %) + "отложить" (15 %) = 100 %.
CATEGORIES = [
    ("Жильё", 35),
    ("Продукты", 20),
    ("Транспорт", 10),
    ("Развлечения", 10),
    ("Здоровье", 5),
    ("Одежда", 5),
]
SAVINGS_PERCENT = 15
INCOME = Decimal("85000")

COMMENTS = {
    "Жильё": ["Квартплата", "Интернет", "Электричество"],
    "Продукты": ["Пятёрочка", "Магнит", "Лента", "ВкусВилл"],
    "Транспорт": ["Метро", "Бензин", "Такси"],
    "Развлечения": ["Кино", "Кафе", "Настолки"],
    "Здоровье": ["Аптека", "Стоматолог"],
    "Одежда": ["Ozon", "Wildberries"],
}


class Command(BaseCommand):
    help = "Создаёт демо-данные для локальной разработки"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            help="логин владельца данных (по умолчанию - первый суперпользователь)",
        )
        parser.add_argument(
            "--months",
            type=int,
            default=3,
            help="сколько последних месяцев заполнить (по умолчанию 3)",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="удалить существующие данные перед созданием",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="разрешить запуск при DEBUG=False",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "DEBUG=False: демо-данные не для продакшена. "
                "Если это действительно нужно - добавьте --force."
            )

        months = options["months"]
        if months < 1:
            raise CommandError("--months должен быть не меньше 1")

        owner = self._owner(options["user"])
        if options["reset"]:
            self._reset(owner)
        elif Category.objects.filter(owner=owner).exists():
            raise CommandError(
                f'У пользователя "{owner.username}" данные уже есть. '
                "Для пересоздания запустите с флагом --reset."
            )

        rng = random.Random(2026)
        categories = self._create_categories(owner)
        self._create_months(owner, months, categories, rng)
        self._create_purchases(owner)

        self.stdout.write(
            self.style.SUCCESS(f'Демо-данные созданы для "{owner.username}":')
        )
        self.stdout.write(
            f"  категорий: {Category.objects.filter(owner=owner).count()}"
        )
        self.stdout.write(
            f"  месяцев:   {BudgetMonth.objects.filter(owner=owner).count()}"
        )
        self.stdout.write(
            f"  трат:      {Transaction.objects.filter(owner=owner).count()}"
        )
        self.stdout.write(
            f"  покупок:   {PlannedPurchase.objects.filter(owner=owner).count()}"
        )

    def _owner(self, username: str | None) -> User:
        """Владелец демо-данных: указанный логин или первый суперпользователь."""
        if username:
            user = User.objects.filter(username=username).first()
            if user is None:
                raise CommandError(f'Пользователь "{username}" не найден')
            return user
        owner = User.objects.filter(is_superuser=True).order_by("pk").first()
        if owner is None:
            raise CommandError(
                "Нет ни одного суперпользователя: создайте его командой "
                "createsuperuser или зарегистрируйтесь на сайте (--user)."
            )
        return owner

    def _reset(self, owner: User) -> None:
        """Удаляет демо-данные владельца, не трогая чужие."""
        with transaction.atomic():
            Transaction.objects.filter(owner=owner).delete()
            PurchaseContribution.objects.filter(purchase__owner=owner).delete()
            PlannedPurchase.objects.filter(owner=owner).delete()
            Allocation.objects.filter(budget_month__owner=owner).delete()
            BudgetMonth.objects.filter(owner=owner).delete()
            Category.objects.filter(owner=owner).delete()
        self.stdout.write("Старые данные удалены.")

    def _create_categories(self, owner: User):
        return {
            name: Category.objects.create(name=name, position=index, owner=owner)
            for index, (name, _percent) in enumerate(CATEGORIES)
        }

    def _create_months(self, owner, months, categories, rng):
        today = timezone.localdate()
        for shift in reversed(range(months)):
            year, month = shift_month(today.year, today.month, -shift)
            budget_month = BudgetMonth.objects.create(
                owner=owner,
                year=year,
                month=month,
                income=INCOME,
                savings_percent=SAVINGS_PERCENT,
            )
            for name, percent in CATEGORIES:
                Allocation.objects.create(
                    budget_month=budget_month,
                    category=categories[name],
                    percent=percent,
                )
                self._create_transactions(
                    owner, budget_month, categories[name], percent, rng, today
                )

    def _create_transactions(self, owner, budget_month, category, percent, rng, today):
        """Траты месяца по категории: факт колеблется вокруг плана."""
        plan_amount = INCOME * percent / 100
        fact = int(plan_amount * Decimal(str(rng.uniform(0.75, 1.2))))
        if fact <= 0:
            return

        amounts = self._split(fact, rng.randint(3, 8), rng)
        last_day = monthrange(budget_month.year, budget_month.month)[1]
        if (budget_month.year, budget_month.month) == (today.year, today.month):
            last_day = today.day

        for amount in amounts:
            Transaction.objects.create(
                owner=owner,
                date=date(
                    budget_month.year, budget_month.month, rng.randint(1, last_day)
                ),
                category=category,
                amount=Decimal(amount),
                comment=rng.choice(COMMENTS[category.name]),
            )

    @staticmethod
    def _split(total: int, parts: int, rng: random.Random) -> list[int]:
        """Делит сумму в целых рублях на части; остаток добирает последняя."""
        weights = [rng.uniform(0.5, 1.5) for _ in range(parts)]
        weight_sum = sum(weights)
        values = [int(total * w / weight_sum) for w in weights]
        values[-1] += total - sum(values)
        return values

    def _create_purchases(self, owner):
        today = timezone.localdate()
        laptop = PlannedPurchase.objects.create(
            owner=owner,
            title="Ноутбук",
            amount=Decimal("90000"),
            priority=1,
            status=PlannedPurchase.Status.SAVING,
        )
        for amount, comment, shift in [
            ("15000", "Первый взнос", 3),
            ("15000", "Второй взнос", 2),
            ("10000", "Третий взнос", 1),
        ]:
            PurchaseContribution.objects.create(
                purchase=laptop,
                amount=Decimal(amount),
                date=self._shift_date(today, shift),
                comment=comment,
            )

        PlannedPurchase.objects.create(
            owner=owner,
            title="Наушники",
            amount=Decimal("12000"),
            priority=2,
            status=PlannedPurchase.Status.WANTED,
        )

        trip = PlannedPurchase.objects.create(
            owner=owner,
            title="Отпуск",
            amount=Decimal("60000"),
            priority=3,
            status=PlannedPurchase.Status.SAVING,
        )
        PurchaseContribution.objects.create(
            purchase=trip,
            amount=Decimal("20000"),
            date=self._shift_date(today, 2),
            comment="Первый взнос",
        )

    def _shift_date(self, day: date, months_back: int) -> date:
        year, month = shift_month(day.year, day.month, -months_back)
        last_day = monthrange(year, month)[1]
        return date(year, month, min(day.day, last_day))

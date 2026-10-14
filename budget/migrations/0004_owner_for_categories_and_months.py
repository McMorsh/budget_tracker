"""Владелец данных "Бюджета": категории и месяцы получают пользователя.

Существующие записи достаются первому пользователю. Если пользователей
нет - данных быть не должно (создать их можно было только из-под входа),
поэтому чистим; траты удаляем первыми, чтобы не упереться в PROTECT
на категориях. Модели соседних приложений на чистой базе могут быть ещё
не созданы - это нормально, там пусто.
"""
from django.conf import settings
from django.db import migrations, models


def assign_or_purge(apps, schema_editor):
    """Отдаёт существующие данные первому пользователю или удаляет их."""
    owner = apps.get_model("auth", "User").objects.order_by("pk").first()
    category = apps.get_model("budget", "Category")
    budget_month = apps.get_model("budget", "BudgetMonth")

    if owner is not None:
        budget_month.objects.update(owner=owner)
        category.objects.update(owner=owner)
        return

    try:
        transaction = apps.get_model("expenses", "Transaction")
    except LookupError:
        transaction = None
    if transaction is not None:
        transaction.objects.all().delete()
    # Месяцы удаляем раньше категорий: их распределения уходят каскадом.
    budget_month.objects.all().delete()
    category.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("budget", "0003_alter_budgetmonth_year"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="categories",
                to=settings.AUTH_USER_MODEL,
                verbose_name="владелец",
            ),
        ),
        migrations.AddField(
            model_name="budgetmonth",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="budget_months",
                to=settings.AUTH_USER_MODEL,
                verbose_name="владелец",
            ),
        ),
        migrations.RunPython(assign_or_purge, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="category",
            name="owner",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="categories",
                to=settings.AUTH_USER_MODEL,
                verbose_name="владелец",
            ),
        ),
        migrations.AlterField(
            model_name="budgetmonth",
            name="owner",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="budget_months",
                to=settings.AUTH_USER_MODEL,
                verbose_name="владелец",
            ),
        ),
        migrations.AlterField(
            model_name="category",
            name="name",
            field=models.CharField(max_length=100, verbose_name="название"),
        ),
        migrations.RemoveConstraint(
            model_name="budgetmonth",
            name="unique_budget_month",
        ),
        migrations.AddConstraint(
            model_name="budgetmonth",
            constraint=models.UniqueConstraint(
                fields=("owner", "year", "month"),
                name="unique_budget_month_per_owner",
            ),
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(
                fields=("owner", "name"),
                name="unique_category_name_per_owner",
            ),
        ),
    ]

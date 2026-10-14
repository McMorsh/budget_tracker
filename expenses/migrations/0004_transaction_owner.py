"""Владелец трат: существующие записи достаются первому пользователю.

Без пользователей данные удаляются - создать траты можно было только
из-под входа (проект ещё не в проде).
"""
from django.conf import settings
from django.db import migrations, models


def assign_or_purge(apps, schema_editor):
    """Отдаёт существующие траты первому пользователю или удаляет их."""
    owner = apps.get_model("auth", "User").objects.order_by("pk").first()
    transaction = apps.get_model("expenses", "Transaction")
    if owner is not None:
        transaction.objects.update(owner=owner)
        return
    transaction.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("expenses", "0003_alter_transaction_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="transactions",
                to=settings.AUTH_USER_MODEL,
                verbose_name="владелец",
            ),
        ),
        migrations.RunPython(assign_or_purge, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="transaction",
            name="owner",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="transactions",
                to=settings.AUTH_USER_MODEL,
                verbose_name="владелец",
            ),
        ),
    ]

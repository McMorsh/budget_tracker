"""Владелец планов покупок: цели достаются первому пользователю.

Взносы привязаны к цели и уходят каскадом. Без пользователей данные
удаляются - проект ещё не в проде.
"""
from django.conf import settings
from django.db import migrations, models


def assign_or_purge(apps, schema_editor):
    """Отдаёт существующие цели первому пользователю или удаляет их."""
    owner = apps.get_model("auth", "User").objects.order_by("pk").first()
    purchase = apps.get_model("purchases", "PlannedPurchase")
    if owner is not None:
        purchase.objects.update(owner=owner)
        return
    purchase.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("purchases", "0003_alter_plannedpurchase_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="plannedpurchase",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="purchases",
                to=settings.AUTH_USER_MODEL,
                verbose_name="владелец",
            ),
        ),
        migrations.RunPython(assign_or_purge, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="plannedpurchase",
            name="owner",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="purchases",
                to=settings.AUTH_USER_MODEL,
                verbose_name="владелец",
            ),
        ),
    ]

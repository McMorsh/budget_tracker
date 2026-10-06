"""Админка приложения «Покупки»."""
from django.contrib import admin

from .models import PlannedPurchase, PurchaseContribution


class PurchaseContributionInline(admin.TabularInline):
    model = PurchaseContribution
    extra = 0


@admin.register(PlannedPurchase)
class PlannedPurchaseAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "amount",
        "status",
        "priority",
        "contributed_display",
        "remaining_display",
    ]
    list_filter = ["status"]
    search_fields = ["title"]
    inlines = [PurchaseContributionInline]

    @admin.display(description="накоплено, ₽")
    def contributed_display(self, obj):
        return obj.contributed

    @admin.display(description="осталось, ₽")
    def remaining_display(self, obj):
        return obj.remaining


@admin.register(PurchaseContribution)
class PurchaseContributionAdmin(admin.ModelAdmin):
    list_display = ["purchase", "date", "amount", "comment"]
    list_filter = ["date"]
    autocomplete_fields = ["purchase"]

"""Админка приложения "Бюджет"."""
from django.contrib import admin

from .models import Allocation, BudgetMonth, Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "position", "is_active"]
    list_editable = ["position", "is_active"]
    list_filter = ["is_active", "owner"]
    search_fields = ["name"]


class AllocationInline(admin.TabularInline):
    model = Allocation
    extra = 1
    autocomplete_fields = ["category"]


@admin.register(BudgetMonth)
class BudgetMonthAdmin(admin.ModelAdmin):
    list_display = ["month_title", "owner", "income", "savings_percent", "plan_total"]
    list_filter = ["year", "owner"]
    inlines = [AllocationInline]

    @admin.display(description="месяц")
    def month_title(self, obj):
        return obj.title

    @admin.display(description="Σ план, %")
    def plan_total(self, obj):
        return obj.planned_total_percent

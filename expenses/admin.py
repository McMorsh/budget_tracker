"""Админка приложения «Траты»."""
from django.contrib import admin

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["date", "category", "amount", "comment"]
    list_filter = ["category", "date"]
    date_hierarchy = "date"
    search_fields = ["comment"]
    autocomplete_fields = ["category"]

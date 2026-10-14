"""Корневой роутинг проекта."""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from reports import views as reports_views

admin.site.site_header = "Budget Tracker"
admin.site.site_title = "Budget Tracker"
admin.site.index_title = "Управление"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", reports_views.home, name="home"),
    path("budget/", include("budget.urls")),
    path("expenses/", include("expenses.urls")),
    path("reports/", include("reports.urls")),
    path("purchases/", include("purchases.urls")),
    # Вход/выход - штатные представления Django; регистрация - accounts.
    # LoginView и signup помечены login_not_required.
    path("accounts/", include("accounts.urls")),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
]

# Media по URL не раздаётся: PDF-отчёты у каждого пользователя свои, их отдаёт
# Django только владельцу (reports.views) - чужой отчёт не скачать даже зная
# путь. Статику (CSS/JS) по-прежнему обслуживает staticfiles.

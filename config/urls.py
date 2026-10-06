"""Корневой роутинг проекта."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import TemplateView

from reports import views as reports_views

admin.site.site_header = "Budget Tracker"
admin.site.site_title = "Budget Tracker"
admin.site.index_title = "Управление"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", reports_views.home, name="home"),
    # Разделы-заглушки: наполняются в своих фазах.
    path(
        "budget/",
        TemplateView.as_view(
            template_name="coming_soon.html",
            extra_context={"section": "Бюджет", "phase": 3},
        ),
        name="budget",
    ),
    path(
        "expenses/",
        TemplateView.as_view(
            template_name="coming_soon.html",
            extra_context={"section": "Траты", "phase": 5},
        ),
        name="expenses",
    ),
    path(
        "purchases/",
        TemplateView.as_view(
            template_name="coming_soon.html",
            extra_context={"section": "Покупки", "phase": 8},
        ),
        name="purchases",
    ),
    # Вход/выход: сайт однопользовательский, регистрации нет.
    # LoginView у Django уже помечен login_not_required.
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

# Media: в разработке отдаёт runserver, в проде — Caddy (sites-infra).
# static() сам возвращает [] при DEBUG=False.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

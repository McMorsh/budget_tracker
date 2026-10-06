"""Корневой роутинг проекта."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path


def stub(request):
    """Временная заглушка главной: каркас UI появится в фазе 2."""
    return HttpResponse("Budget Tracker")


admin.site.site_header = "Budget Tracker"
admin.site.site_title = "Budget Tracker"
admin.site.index_title = "Управление"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", stub, name="home"),
]

# Media: в разработке отдаёт runserver, в проде — Caddy (sites-infra).
# static() сам возвращает [] при DEBUG=False.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

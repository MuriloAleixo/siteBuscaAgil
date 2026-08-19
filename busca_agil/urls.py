from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve

from core import views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/index.html", permanent=False)),
    path(
        "favicon.ico",
        RedirectView.as_view(url=settings.STATIC_URL + "img/favicon.svg", permanent=True),
    ),
    # Login com Google (allauth): /accounts/google/login/ inicia o fluxo,
    # /accounts/google/login/callback/ recebe a volta do Google.
    path("accounts/", include("allauth.urls")),
    path("", include("core.urls")),
    path("css/<path:path>", serve, {"document_root": settings.BASE_DIR / "css"}),
    path("js/<path:path>", serve, {"document_root": settings.BASE_DIR / "js"}),
    path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
]

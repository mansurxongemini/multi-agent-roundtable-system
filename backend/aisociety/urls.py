"""Root URL configuration: admin, REST API, and the SPA shell."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    # Single-page minimalist frontend served from frontend/index.html.
    path("", TemplateView.as_view(template_name="index.html"), name="home"),
]

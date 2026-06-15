"""REST API routing."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AIAgentViewSet,
    GroupMembershipViewSet,
    GroupViewSet,
    ProviderViewSet,
    adapter_types,
)

router = DefaultRouter()
router.register(r"providers", ProviderViewSet, basename="provider")
router.register(r"agents", AIAgentViewSet, basename="agent")
router.register(r"groups", GroupViewSet, basename="group")
router.register(r"memberships", GroupMembershipViewSet, basename="membership")

urlpatterns = [
    path("meta/adapters/", adapter_types, name="adapter-types"),
    path("", include(router.urls)),
]

"""WebSocket URL routing (consumed by aisociety/asgi.py)."""

from django.urls import re_path

from orchestration.consumers import GroupConsumer

websocket_urlpatterns = [
    # One socket per room; group_id is a UUID.
    re_path(r"^ws/groups/(?P<group_id>[0-9a-f-]+)/$", GroupConsumer.as_asgi()),
]

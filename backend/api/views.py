"""
REST API views.

Covers full CRUD for Providers, Agents, Groups, and Group memberships, plus a
few action endpoints:
  * POST /api/providers/{id}/test/        -> live connectivity check
  * POST /api/agents/{id}/test/           -> single-shot generation probe
  * GET  /api/groups/{id}/messages/       -> paginated chat history
  * POST /api/groups/{id}/members/        -> assign an agent to the group
  * GET  /api/meta/adapters/              -> available provider adapter types

The realtime simulation controls (start/pause/stop, God Mode) are driven over
the WebSocket, not REST, so they are intentionally not duplicated here.
"""

from __future__ import annotations

import asyncio

from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from core.models import AIAgent, Group, GroupMembership, Message, Provider
from providers.base import ProviderError
from providers.router import available_adapter_types, get_adapter_for_provider

from .serializers import (
    AIAgentSerializer,
    GroupMembershipSerializer,
    GroupSerializer,
    MessageSerializer,
    ProviderSerializer,
)


class ProviderViewSet(viewsets.ModelViewSet):
    queryset = Provider.objects.all()
    serializer_class = ProviderSerializer

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Fire a tiny completion to verify the key/endpoint actually work."""
        provider = self.get_object()
        model = request.data.get("model", "")
        if not model:
            return Response(
                {"ok": False, "error": "Provide a `model` to test against."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        adapter = get_adapter_for_provider(provider)
        try:
            result = asyncio.run(
                adapter.generate(
                    messages=[{"role": "user", "content": "Reply with the single word: pong"}],
                    system_prompt="You are a connectivity probe.",
                    model=model,
                    temperature=0.0,
                    max_tokens=8,
                )
            )
            return Response({"ok": True, "sample": result.text})
        except ProviderError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


class AIAgentViewSet(viewsets.ModelViewSet):
    queryset = AIAgent.objects.select_related("provider").all()
    serializer_class = AIAgentSerializer

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Single-shot generation using the agent's own persona/config."""
        agent = self.get_object()
        prompt = request.data.get("prompt", "Introduce yourself in one sentence.")
        adapter = get_adapter_for_provider(agent.provider)
        try:
            result = asyncio.run(
                adapter.generate(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=agent.system_prompt,
                    model=agent.model_id,
                    temperature=agent.temperature,
                    max_tokens=agent.max_tokens,
                )
            )
            return Response({"ok": True, "text": result.text, "tokens": result.total_tokens})
        except ProviderError as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.prefetch_related("memberships__agent").all()
    serializer_class = GroupSerializer

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        """Paginated chat history (newest-last)."""
        group = self.get_object()
        qs = (
            Message.objects.filter(group=group, kind=Message.Kind.CHAT)
            .select_related("agent")
            .order_by("created_at")
        )
        page = self.paginate_queryset(qs)
        serializer = MessageSerializer(page if page is not None else qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"])
    def members(self, request, pk=None):
        """List members (GET) or assign an agent to this group (POST)."""
        group = self.get_object()
        if request.method == "GET":
            data = GroupMembershipSerializer(group.memberships.all(), many=True).data
            return Response(data)

        agent_id = request.data.get("agent")
        if not agent_id:
            return Response({"error": "`agent` is required."}, status=400)
        membership, _ = GroupMembership.objects.get_or_create(
            group=group,
            agent_id=agent_id,
            defaults={"turn_order": group.memberships.count()},
        )
        # Allow setting turn_order on (re)assignment.
        if "turn_order" in request.data:
            membership.turn_order = int(request.data["turn_order"])
            membership.save(update_fields=["turn_order"])
        return Response(GroupMembershipSerializer(membership).data, status=201)

    @action(detail=True, methods=["delete"], url_path=r"members/(?P<agent_id>[^/.]+)")
    def remove_member(self, request, pk=None, agent_id=None):
        group = self.get_object()
        GroupMembership.objects.filter(group=group, agent_id=agent_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GroupMembershipViewSet(viewsets.ModelViewSet):
    queryset = GroupMembership.objects.select_related("agent", "group").all()
    serializer_class = GroupMembershipSerializer


@api_view(["GET"])
def adapter_types(request):
    """Discover which provider adapters this deployment supports."""
    return Response({"adapter_types": available_adapter_types()})

"""
DRF serializers.

Security note: `Provider.api_key` is WRITE-ONLY. The frontend can submit a key
(which gets encrypted at rest by EncryptedTextField) but can never read it back
— responses only expose a boolean `has_key`. Keys never leave the backend.
"""

from rest_framework import serializers

from core.models import AIAgent, Group, GroupMembership, Message, Provider
from providers.router import available_adapter_types


class ProviderSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_key = serializers.BooleanField(read_only=True)

    class Meta:
        model = Provider
        fields = [
            "id", "name", "adapter_type", "base_url",
            "api_key", "has_key", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_adapter_type(self, value):
        if value not in available_adapter_types():
            raise serializers.ValidationError(
                f"Unknown adapter_type. Choose one of {available_adapter_types()}."
            )
        return value

    def update(self, instance, validated_data):
        # Empty api_key on update => keep the existing one (don't wipe it).
        if validated_data.get("api_key", None) == "":
            validated_data.pop("api_key")
        return super().update(instance, validated_data)


class AIAgentSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.name", read_only=True)
    adapter_type = serializers.CharField(source="provider.adapter_type", read_only=True)

    class Meta:
        model = AIAgent
        fields = [
            "id", "provider", "provider_name", "adapter_type",
            "name", "avatar_color", "avatar_emoji",
            "model_id", "system_prompt", "temperature", "max_tokens",
            "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class GroupMembershipSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.name", read_only=True)
    agent_color = serializers.CharField(source="agent.avatar_color", read_only=True)
    agent_emoji = serializers.CharField(source="agent.avatar_emoji", read_only=True)
    model_id = serializers.CharField(source="agent.model_id", read_only=True)

    class Meta:
        model = GroupMembership
        fields = [
            "id", "group", "agent", "agent_name", "agent_color", "agent_emoji",
            "model_id", "turn_order", "is_muted", "priority_floor", "turn_count",
        ]
        read_only_fields = ["id", "turn_count"]


class GroupSerializer(serializers.ModelSerializer):
    memberships = GroupMembershipSerializer(many=True, read_only=True)
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            "id", "name", "description", "topic", "status", "turn_mode",
            "speed_ms", "context_window", "rolling_summary",
            "memberships", "member_count", "created_at",
        ]
        read_only_fields = ["id", "status", "rolling_summary", "created_at"]

    def get_member_count(self, obj) -> int:
        return obj.memberships.count()


class MessageSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.name", read_only=True)
    agent_color = serializers.CharField(source="agent.avatar_color", read_only=True)
    agent_emoji = serializers.CharField(source="agent.avatar_emoji", read_only=True)

    class Meta:
        model = Message
        fields = [
            "id", "group", "agent", "agent_name", "agent_color", "agent_emoji",
            "role", "kind", "content", "tokens_used", "response_ms", "created_at",
        ]
        read_only_fields = fields

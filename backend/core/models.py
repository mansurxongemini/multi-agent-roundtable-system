"""
Database models for the AI Society Simulation.

Entity map
----------
Provider          A configured LLM vendor + (encrypted) API key. Pluggable via
                  an `adapter_type` that maps to a concrete adapter class.
AIAgent           A persona: provider + model + system prompt + sampling params.
Group             A "room" with its own autonomous simulation, topic, status,
                  pacing, sliding-window size, and rolling summary.
GroupMembership   Which agents belong to a group + per-room turn order and the
                  live God-Mode flags (mute / priority floor).
Message           A single utterance (agent, human/admin, or system). Also used
                  to persist rolling-summary checkpoints (kind=SUMMARY).
"""

from __future__ import annotations

import uuid

from django.db import models

from core.fields import EncryptedTextField


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ─────────────────────────────────────────────────────────────────────────────
# 1. Provider hub
# ─────────────────────────────────────────────────────────────────────────────
class Provider(TimestampedModel):
    """A dynamically configurable LLM provider (Groq, Gemini, OpenAI, custom…)."""

    class AdapterType(models.TextChoices):
        GROQ = "groq", "Groq"
        GEMINI = "gemini", "Google Gemini"
        OPENAI = "openai", "OpenAI"
        ANTHROPIC = "anthropic", "Anthropic"
        CUSTOM = "custom", "Custom (OpenAI-compatible)"

    name = models.CharField(max_length=120)
    # Drives the adapter-pattern factory (providers.router.get_adapter).
    adapter_type = models.CharField(max_length=32, choices=AdapterType.choices)
    # Optional override; each adapter ships a sensible default base URL.
    base_url = models.URLField(blank=True, default="")
    # Encrypted at rest; only ever decrypted server-side.
    api_key = EncryptedTextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.adapter_type})"

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Agent / persona
# ─────────────────────────────────────────────────────────────────────────────
class AIAgent(TimestampedModel):
    """A configurable AI persona bound to a provider + model."""

    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, related_name="agents"
    )
    name = models.CharField(max_length=120)
    avatar_color = models.CharField(max_length=9, default="#7C3AED")  # hex
    avatar_emoji = models.CharField(max_length=8, default="🤖")

    model_id = models.CharField(
        max_length=120, help_text="e.g. llama3-70b-8192, gemini-1.5-flash, gpt-4o-mini"
    )
    # The persona. Injected as the system message for every call.
    system_prompt = models.TextField(
        default="You are a thoughtful participant in a group discussion."
    )

    temperature = models.FloatField(default=0.7)
    max_tokens = models.PositiveIntegerField(default=512)

    # Global kill switch (independent of per-room mute).
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.avatar_emoji} {self.name} [{self.model_id}]"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Group / room
# ─────────────────────────────────────────────────────────────────────────────
class Group(TimestampedModel):
    """A chat room running its own autonomous, continuous simulation."""

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        PAUSED = "paused", "Paused"
        STOPPED = "stopped", "Stopped"

    class TurnMode(models.TextChoices):
        SEQUENTIAL = "sequential", "Sequential (round-robin)"
        RANDOM = "random", "Random (no immediate repeat)"
        WEIGHTED = "weighted", "Weighted (quieter agents favoured)"

    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    # The current discussion subject; can be hot-swapped via God Mode.
    topic = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.STOPPED
    )
    turn_mode = models.CharField(
        max_length=16, choices=TurnMode.choices, default=TurnMode.SEQUENTIAL
    )

    # Pacing: delay between agent turns (ms).
    speed_ms = models.PositiveIntegerField(default=3000)
    # Sliding window: how many recent messages are sent verbatim to agents.
    context_window = models.PositiveIntegerField(default=20)

    # Infinite-memory machinery: the compressed digest of everything older than
    # the sliding window. Rebuilt asynchronously by orchestration.tasks.
    rolling_summary = models.TextField(blank=True, default="")
    # Watermark: messages at/below this point are already folded into the
    # rolling_summary and need not be re-summarised.
    summarized_until = models.DateTimeField(null=True, blank=True)

    agents = models.ManyToManyField(
        AIAgent, through="GroupMembership", related_name="groups"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_running(self) -> bool:
        return self.status == self.Status.RUNNING


class GroupMembership(TimestampedModel):
    """Through-model: an agent's participation in a specific group/room."""

    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="memberships"
    )
    agent = models.ForeignKey(
        AIAgent, on_delete=models.CASCADE, related_name="memberships"
    )

    # Position in the sequential rotation (lower = earlier).
    turn_order = models.PositiveIntegerField(default=0)

    # ── God-Mode live flags ──────────────────────────────────────────────
    # Muted agents are skipped by the turn manager entirely.
    is_muted = models.BooleanField(default=False)
    # When set, the agent jumps the queue and speaks next regardless of mode.
    priority_floor = models.BooleanField(default=False)

    # Lightweight activity accounting (used by weighted turn mode + analytics).
    turn_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["turn_order", "created_at"]
        unique_together = ("group", "agent")

    def __str__(self) -> str:
        return f"{self.agent.name} @ {self.group.name}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Message
# ─────────────────────────────────────────────────────────────────────────────
class Message(TimestampedModel):
    """A single utterance in a group, or a rolling-summary checkpoint."""

    class Role(models.TextChoices):
        AGENT = "agent", "Agent"
        HUMAN = "human", "Human / Admin (God)"
        SYSTEM = "system", "System"

    class Kind(models.TextChoices):
        CHAT = "chat", "Chat"
        SUMMARY = "summary", "Rolling summary checkpoint"

    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="messages"
    )
    # NULL agent => human or system message.
    agent = models.ForeignKey(
        AIAgent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )

    role = models.CharField(max_length=12, choices=Role.choices, default=Role.AGENT)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.CHAT)
    content = models.TextField()

    # Telemetry.
    tokens_used = models.PositiveIntegerField(default=0)
    response_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["group", "created_at"]),
            models.Index(fields=["group", "kind"]),
        ]

    def __str__(self) -> str:
        who = self.agent.name if self.agent else self.get_role_display()
        return f"[{self.group.name}] {who}: {self.content[:40]}"

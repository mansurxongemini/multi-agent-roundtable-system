"""
Simulation Engine — the autonomous orchestration loop.

One `asyncio.Task` runs per *running* group, hosted inside the ASGI process.
The engine is a process-singleton (`engine`) that the WebSocket consumer drives:
start/pause/stop a room, inject a human message, force an agent via the priority
floor, mute/unmute, or change speed. The loop itself:

    while running:
        membership = TurnManager.select_next(eligible, ...)   # respects God Mode
        context     = MemoryManager.build_context(...)        # sliding window
        result      = adapter.generate(...)                   # provider call + retries
        if result.text == "[SKIP]":                           # free will
            -> suppress, do NOT persist, broadcast a soft "skipped" event
        else:
            -> persist Message, broadcast "message", maybe trigger summary
        await sleep(speed_ms)

Everything is broadcast over the Channels layer to group `group_<id>` so every
connected admin sees the same realtime stream.

Robustness:
  * Provider errors retry with exponential backoff; after MAX_RETRIES the agent
    is skipped for this turn (loop never crashes).
  * The loop re-reads group status + membership flags every iteration, so God
    Mode actions (pause, mute, priority floor, speed) take effect immediately.
  * When un-summarised tokens exceed the threshold, a Celery summarization task
    is enqueued without blocking the loop.
"""

from __future__ import annotations

import asyncio
import logging
import time

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings

from core.models import Group, GroupMembership, Message
from orchestration import memory, turn_manager
from orchestration.prompts import build_persona
from providers.base import ProviderError, RateLimitError
from providers.router import get_adapter_for_provider

logger = logging.getLogger(__name__)

_CFG = settings.ORCHESTRATION
SKIP_TOKEN = _CFG["SKIP_TOKEN"]
MAX_RETRIES = _CFG["MAX_RETRIES"]
SUMMARY_THRESHOLD = _CFG["SUMMARY_TOKEN_THRESHOLD"]


def group_channel(group_id) -> str:
    return f"group_{group_id}"


class SimulationEngine:
    """Owns and supervises one background loop per running group."""

    def __init__(self) -> None:
        # group_id(str) -> asyncio.Task
        self._tasks: dict[str, asyncio.Task] = {}
        self._channel_layer = get_channel_layer()

    # ── Lifecycle control (called by the consumer) ───────────────────────
    async def start(self, group_id: str) -> None:
        group_id = str(group_id)
        if group_id in self._tasks and not self._tasks[group_id].done():
            return  # already running
        await self._set_status(group_id, Group.Status.RUNNING)
        self._tasks[group_id] = asyncio.create_task(self._run_loop(group_id))
        logger.info("Simulation started for group %s", group_id)

    async def pause(self, group_id: str) -> None:
        await self._set_status(str(group_id), Group.Status.PAUSED)
        # The loop observes the status change and idles without dying.

    async def stop(self, group_id: str) -> None:
        group_id = str(group_id)
        await self._set_status(group_id, Group.Status.STOPPED)
        task = self._tasks.pop(group_id, None)
        if task and not task.done():
            task.cancel()
        logger.info("Simulation stopped for group %s", group_id)

    def is_running(self, group_id: str) -> bool:
        task = self._tasks.get(str(group_id))
        return bool(task and not task.done())

    # ── God Mode helpers ─────────────────────────────────────────────────
    async def inject_human_message(self, group_id: str, content: str) -> dict:
        """Persist an admin message and broadcast it. Agents pick it up next turn."""
        msg = await self._create_message(
            group_id, agent=None, role=Message.Role.HUMAN, content=content
        )
        await self._broadcast(group_id, "message", self._serialize(msg))
        return self._serialize(msg)

    async def set_priority_floor(self, group_id: str, agent_id: str, on: bool) -> None:
        await sync_to_async(
            GroupMembership.objects.filter(
                group_id=group_id, agent_id=agent_id
            ).update
        )(priority_floor=on)
        await self._broadcast(
            group_id, "agent_flag",
            {"agent_id": str(agent_id), "priority_floor": on},
        )

    async def set_muted(self, group_id: str, agent_id: str, muted: bool) -> None:
        await sync_to_async(
            GroupMembership.objects.filter(
                group_id=group_id, agent_id=agent_id
            ).update
        )(is_muted=muted)
        await self._broadcast(
            group_id, "agent_flag", {"agent_id": str(agent_id), "is_muted": muted}
        )

    async def set_speed(self, group_id: str, speed_ms: int) -> None:
        await sync_to_async(
            Group.objects.filter(id=group_id).update
        )(speed_ms=max(250, int(speed_ms)))

    async def set_topic(self, group_id: str, topic: str) -> dict:
        await sync_to_async(Group.objects.filter(id=group_id).update)(topic=topic)
        # Surface the change as a system message so agents pivot.
        msg = await self._create_message(
            group_id, agent=None, role=Message.Role.SYSTEM,
            content=f"Topic changed to: {topic}",
        )
        await self._broadcast(group_id, "topic_changed", {"topic": topic})
        await self._broadcast(group_id, "message", self._serialize(msg))
        return self._serialize(msg)

    # ── The loop ─────────────────────────────────────────────────────────
    async def _run_loop(self, group_id: str) -> None:
        last_speaker_id = None
        recent_speaker_ids: list = []
        try:
            while True:
                group = await self._get_group(group_id)
                if group is None or group.status == Group.Status.STOPPED:
                    break
                if group.status == Group.Status.PAUSED:
                    await asyncio.sleep(0.5)  # idle, stay alive
                    continue

                eligible = await self._eligible_members(group_id)
                if not eligible:
                    await self._broadcast(
                        group_id, "info",
                        {"message": "No eligible agents — add or unmute agents."},
                    )
                    await asyncio.sleep(1.0)
                    continue

                membership = turn_manager.select_next(
                    eligible, group.turn_mode, last_speaker_id, recent_speaker_ids
                )
                if membership is None:
                    await asyncio.sleep(0.5)
                    continue

                # Consume a one-shot priority floor so it fires exactly once.
                if membership.priority_floor:
                    await self.set_priority_floor(group_id, membership.agent_id, False)

                spoke = await self._take_turn(group, membership)

                last_speaker_id = membership.agent_id
                recent_speaker_ids.append(membership.agent_id)
                recent_speaker_ids = recent_speaker_ids[-5:]

                # Pace the conversation (re-read speed each turn).
                await asyncio.sleep(group.speed_ms / 1000.0)

                # Opportunistically compress long histories off-loop.
                if spoke:
                    await self._maybe_summarize(group_id)
        except asyncio.CancelledError:  # graceful stop
            raise
        except Exception:  # never let the loop die silently
            logger.exception("Loop crashed for group %s", group_id)
            await self._broadcast(group_id, "error", {"message": "Loop error; paused."})
            await self._set_status(group_id, Group.Status.PAUSED)

    async def _take_turn(self, group: Group, membership: GroupMembership) -> bool:
        """Run one agent's turn. Returns True if the agent actually spoke."""
        agent = membership.agent
        await self._broadcast(
            group.id, "thinking", {"agent_id": str(agent.id), "name": agent.name}
        )

        context = await sync_to_async(memory.build_context)(group, agent)
        persona = build_persona(agent.name, agent.system_prompt, group.topic)
        adapter = get_adapter_for_provider(agent.provider)

        started = time.monotonic()
        result = await self._generate_with_retry(
            adapter, agent, context, persona, group.id
        )
        if result is None:
            await self._broadcast(
                group.id, "skipped",
                {"agent_id": str(agent.id), "reason": "provider_error"},
            )
            return False

        elapsed_ms = int((time.monotonic() - started) * 1000)
        text = result.text.strip()

        # ── Free will: [SKIP] => suppress, do not persist ────────────────
        if not text or SKIP_TOKEN in text:
            await self._broadcast(
                group.id, "skipped",
                {"agent_id": str(agent.id), "reason": "skip"},
            )
            # Still count the turn so the rotation advances fairly.
            await self._bump_turn(membership.id, spoke=False)
            return False

        msg = await self._create_message(
            group.id, agent=agent, role=Message.Role.AGENT, content=text,
            tokens_used=result.total_tokens, response_ms=elapsed_ms,
        )
        await self._bump_turn(membership.id, spoke=True)
        await self._broadcast(group.id, "message", self._serialize(msg))
        return True

    async def _generate_with_retry(self, adapter, agent, context, persona, group_id):
        delay = 1.0
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return await adapter.generate(
                    messages=context,
                    system_prompt=persona,
                    model=agent.model_id,
                    temperature=agent.temperature,
                    max_tokens=agent.max_tokens,
                )
            except RateLimitError:
                logger.warning("Rate limited (%s) attempt %d", agent.name, attempt)
                await asyncio.sleep(delay)
                delay *= 2  # exponential backoff
            except ProviderError as exc:
                logger.error("Provider error for %s: %s", agent.name, exc)
                await self._broadcast(
                    group_id, "error",
                    {"agent_id": str(agent.id), "message": str(exc)[:200]},
                )
                return None
        return None  # exhausted retries

    async def _maybe_summarize(self, group_id: str) -> None:
        group = await self._get_group(group_id)
        if group is None:
            return
        tokens = await sync_to_async(memory.raw_token_estimate)(group)
        if tokens < SUMMARY_THRESHOLD:
            return
        try:
            from orchestration.tasks import compress_history

            compress_history.delay(str(group_id))  # fire-and-forget (Celery)
            await self._broadcast(group_id, "summarizing", {"tokens": tokens})
        except Exception:
            # Celery/broker unavailable — run inline as a fallback.
            logger.warning("Celery unavailable; summarizing inline for %s", group_id)
            from orchestration.tasks import compress_history

            await sync_to_async(compress_history)(str(group_id))

    # ── DB helpers (sync ORM wrapped for the async loop) ─────────────────
    @sync_to_async
    def _get_group(self, group_id):
        return Group.objects.filter(id=group_id).first()

    @sync_to_async
    def _eligible_members(self, group_id):
        return list(
            GroupMembership.objects.select_related("agent__provider")
            .filter(
                group_id=group_id,
                is_muted=False,
                agent__is_active=True,
                agent__provider__is_active=True,
            )
        )

    @sync_to_async
    def _set_status(self, group_id, status):
        Group.objects.filter(id=group_id).update(status=status)

    @sync_to_async
    def _bump_turn(self, membership_id, spoke):
        from django.db.models import F

        GroupMembership.objects.filter(id=membership_id).update(
            turn_count=F("turn_count") + 1
        )

    @sync_to_async
    def _create_message(self, group_id, *, agent, role, content,
                        tokens_used=0, response_ms=0):
        return Message.objects.create(
            group_id=group_id, agent=agent, role=role, content=content,
            tokens_used=tokens_used, response_ms=response_ms,
        )

    # ── Serialization + broadcasting ─────────────────────────────────────
    @staticmethod
    def _serialize(msg: Message) -> dict:
        return {
            "id": str(msg.id),
            "group_id": str(msg.group_id),
            "agent_id": str(msg.agent_id) if msg.agent_id else None,
            "agent_name": msg.agent.name if msg.agent else None,
            "agent_color": msg.agent.avatar_color if msg.agent else None,
            "agent_emoji": msg.agent.avatar_emoji if msg.agent else None,
            "role": msg.role,
            "content": msg.content,
            "tokens_used": msg.tokens_used,
            "response_ms": msg.response_ms,
            "created_at": msg.created_at.isoformat(),
        }

    async def _broadcast(self, group_id, event: str, data: dict) -> None:
        await self._channel_layer.group_send(
            group_channel(group_id),
            {"type": "sim.event", "event": event, "data": data},
        )


# Process-wide singleton used by the consumer.
engine = SimulationEngine()

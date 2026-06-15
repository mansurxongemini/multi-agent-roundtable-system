"""
Background tasks (Celery).

The flagship task is `compress_history`, which implements the "Rolling Summary"
half of the infinite-memory system. When a group's un-summarised history grows
past the configured token threshold, the engine enqueues this task. It:

  1. Loads all chat messages newer than `group.summarized_until`, except the
     ones currently inside the verbatim sliding window (those stay live).
  2. Asks an LLM (the group's first available provider, or an explicit
     summarizer) to fold them into the existing `rolling_summary`.
  3. Persists the new summary and advances the `summarized_until` watermark.

Because it runs off the realtime loop, agents keep talking uninterrupted while
older context is being compressed.
"""

from __future__ import annotations

import asyncio
import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from core.models import Group, Message
from orchestration.prompts import SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_TEMPLATE
from providers.base import ProviderError
from providers.router import get_adapter_for_provider

logger = logging.getLogger(__name__)


def _pick_summarizer(group: Group):
    """Choose an (adapter, model) pair to perform summarization.

    Strategy: use the provider of the first active member agent. This keeps the
    summarizer co-located with at least one working API key.
    """
    membership = (
        group.memberships.select_related("agent__provider")
        .filter(agent__is_active=True, agent__provider__is_active=True)
        .first()
    )
    if not membership:
        return None, None
    agent = membership.agent
    adapter = get_adapter_for_provider(agent.provider)
    return adapter, agent.model_id


@shared_task(name="orchestration.compress_history")
def compress_history(group_id: str) -> str:
    """Fold older messages into the group's rolling summary. Returns a status."""
    try:
        group = Group.objects.get(id=group_id)
    except Group.DoesNotExist:
        return "group-missing"

    window = group.context_window

    # Ids of messages inside the live verbatim window — never summarise these.
    live_ids = list(
        group.messages.filter(kind=Message.Kind.CHAT)
        .order_by("-created_at")
        .values_list("id", flat=True)[:window]
    )

    pending_qs = group.messages.filter(kind=Message.Kind.CHAT).exclude(id__in=live_ids)
    if group.summarized_until:
        pending_qs = pending_qs.filter(created_at__gt=group.summarized_until)
    pending = list(pending_qs.order_by("created_at"))

    if not pending:
        return "nothing-to-summarize"

    transcript = "\n".join(_render(m) for m in pending)

    adapter, model = _pick_summarizer(group)
    if adapter is None:
        logger.warning("No summarizer available for group %s", group_id)
        return "no-summarizer"

    user_prompt = SUMMARY_USER_TEMPLATE.format(
        previous_summary=group.rolling_summary or "(none)",
        transcript=transcript,
    )

    try:
        result = asyncio.run(
            adapter.generate(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                model=model,
                temperature=0.3,
                max_tokens=600,
            )
        )
    except ProviderError as exc:
        logger.error("Summarization failed for group %s: %s", group_id, exc)
        return f"error:{exc}"

    group.rolling_summary = result.text
    # Advance watermark to the newest message we just folded in.
    group.summarized_until = pending[-1].created_at
    group.save(update_fields=["rolling_summary", "summarized_until", "updated_at"])

    # Persist a SUMMARY checkpoint for auditability (not shown as a chat bubble).
    Message.objects.create(
        group=group,
        role=Message.Role.SYSTEM,
        kind=Message.Kind.SUMMARY,
        content=result.text,
        tokens_used=result.total_tokens,
    )
    logger.info("Rolling summary updated for group %s (%d msgs)", group_id, len(pending))
    return f"summarized:{len(pending)}"


def _render(msg: Message) -> str:
    if msg.role == Message.Role.HUMAN:
        who = "[ADMIN/GOD]"
    elif msg.role == Message.Role.SYSTEM:
        who = "[SYSTEM]"
    else:
        who = msg.agent.name if msg.agent else "Unknown"
    return f"{who}: {msg.content}"

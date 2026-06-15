"""
Memory Manager — infinite memory via sliding window + rolling summary.

For any given speaking agent we build a provider-neutral message list:

    [
      {role: "user",      content: "<rolling summary of older history>"},   # if any
      {role: "assistant", content: "<that agent's own past line>"},          # self = assistant
      {role: "user",      content: "OtherAgent: <line>"},                    # others/human = user
      ...
    ]

Only the last `context_window` messages are sent verbatim. Everything older is
represented by `group.rolling_summary`, which a background Celery task keeps up
to date (see tasks.py). This keeps every call comfortably under the model's
context limit, so agents never crash or hallucinate from token overflow.
"""

from __future__ import annotations

from core.models import Group, Message

try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text or ""))

except Exception:  # tiktoken unavailable -> cheap heuristic (~4 chars/token)
    def count_tokens(text: str) -> int:
        return max(1, len(text or "") // 4)


def build_context(group: Group, speaker, window_size: int | None = None) -> list[dict]:
    """Assemble the message list for `speaker`'s next turn.

    `speaker` is the AIAgent about to talk. Its own previous messages are mapped
    to role="assistant"; everyone else (agents, humans, system) maps to "user"
    with a "Name: " prefix so the model can attribute each line.
    """
    window = window_size or group.context_window

    # Newest `window` chat messages, chronological order.
    recent_qs = (
        group.messages.filter(kind=Message.Kind.CHAT)
        .order_by("-created_at")[:window]
    )
    recent = list(reversed(list(recent_qs)))

    context: list[dict] = []

    # Lead with the rolling summary so the agent retains long-term memory.
    if group.rolling_summary:
        context.append(
            {
                "role": "user",
                "content": f"[CONVERSATION SO FAR — SUMMARY]\n{group.rolling_summary}",
            }
        )

    for msg in recent:
        if msg.role == Message.Role.AGENT and msg.agent_id == speaker.id:
            # The speaker's own past utterances are its assistant history.
            context.append({"role": "assistant", "content": msg.content})
        else:
            label = _label_for(msg)
            context.append({"role": "user", "content": f"{label}: {msg.content}"})

    # If nobody has spoken yet, prime the discussion with the topic.
    if not recent:
        seed = group.topic or "Begin an open discussion. Introduce yourself briefly."
        context.append({"role": "user", "content": f"[ADMIN/GOD]: {seed}"})

    return context


def _label_for(msg: Message) -> str:
    if msg.role == Message.Role.HUMAN:
        return "[ADMIN/GOD]"
    if msg.role == Message.Role.SYSTEM:
        return "[SYSTEM]"
    if msg.agent:
        return msg.agent.name
    return "Unknown"


def raw_token_estimate(group: Group) -> int:
    """Approximate total tokens of un-summarised chat history.

    Used by the engine to decide when to trigger background compression.
    """
    qs = group.messages.filter(kind=Message.Kind.CHAT)
    if group.summarized_until:
        qs = qs.filter(created_at__gt=group.summarized_until)
    return sum(count_tokens(c) for c in qs.values_list("content", flat=True))

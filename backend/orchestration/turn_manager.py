"""
Turn Manager — decides who speaks next.

Operates purely on a list of "eligible" GroupMembership rows (muted/inactive
agents are filtered out before we get here). It honours the room's `turn_mode`
and, crucially, the God-Mode **priority floor**: any membership flagged
`priority_floor=True` jumps the queue immediately.

This module is intentionally synchronous and side-effect free except for
`mark_spoke`, which bumps activity counters used by the weighted mode.
"""

from __future__ import annotations

import random

from core.models import GroupMembership


def select_next(
    eligible: list[GroupMembership],
    turn_mode: str,
    last_speaker_id=None,
    recent_speaker_ids: list | None = None,
) -> GroupMembership | None:
    """Return the membership that should speak next, or None if nobody can."""
    if not eligible:
        return None

    # 1) Priority floor (God Mode) always wins, regardless of turn mode.
    forced = [m for m in eligible if m.priority_floor]
    if forced:
        # Earliest-flagged (lowest turn_order) goes first if several are set.
        return sorted(forced, key=lambda m: m.turn_order)[0]

    # 2) Normal selection by mode.
    if turn_mode == "random":
        return _select_random(eligible, recent_speaker_ids or [])
    if turn_mode == "weighted":
        return _select_weighted(eligible)
    # Default: sequential round-robin.
    return _select_sequential(eligible, last_speaker_id)


def _select_sequential(eligible, last_speaker_id):
    ordered = sorted(eligible, key=lambda m: (m.turn_order, str(m.agent_id)))
    if last_speaker_id is None:
        return ordered[0]
    ids = [m.agent_id for m in ordered]
    if last_speaker_id in ids:
        idx = ids.index(last_speaker_id)
        return ordered[(idx + 1) % len(ordered)]
    return ordered[0]


def _select_random(eligible, recent_speaker_ids):
    # Avoid immediate repeats: exclude the last couple of speakers if possible.
    avoid = set(recent_speaker_ids[-2:])
    pool = [m for m in eligible if m.agent_id not in avoid] or eligible
    return random.choice(pool)


def _select_weighted(eligible):
    # Quieter agents (lower turn_count) get proportionally higher odds.
    max_count = max((m.turn_count for m in eligible), default=0)
    weights = [(max_count - m.turn_count + 1) for m in eligible]
    return random.choices(eligible, weights=weights, k=1)[0]

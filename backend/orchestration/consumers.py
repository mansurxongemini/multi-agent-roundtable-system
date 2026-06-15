"""
WebSocket consumer for a single group/room.

URL: ws://<host>/ws/groups/<group_id>/

The browser (the human "God/Admin") connects per room. Inbound commands drive
the SimulationEngine; outbound events are the realtime stream the engine
broadcasts to every connected admin of that room.

Inbound command protocol (JSON `{"action": ..., ...}`)
------------------------------------------------------
  {"action": "start"}                                  -> begin/resume the loop
  {"action": "pause"}                                  -> pause (loop idles)
  {"action": "stop"}                                   -> stop & cancel the loop
  {"action": "human_message", "content": "..."}        -> inject admin message
  {"action": "priority_floor", "agent_id": "..", "on": true}  -> force agent next
  {"action": "mute", "agent_id": "..", "muted": true}  -> mute/unmute an agent
  {"action": "set_speed", "speed_ms": 1500}            -> change pacing
  {"action": "set_topic", "topic": "..."}              -> hot-swap the topic

Outbound event protocol (JSON `{"event": ..., "data": ...}`)
-----------------------------------------------------------
  thinking | message | skipped | topic_changed | agent_flag |
  summarizing | status | error | info | history (initial backlog)
"""

from __future__ import annotations

import json

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from core.models import Group, Message
from orchestration.engine import engine, group_channel


class GroupConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_id = self.scope["url_route"]["kwargs"]["group_id"]
        self.channel_group = group_channel(self.group_id)

        group = await self._get_group()
        if group is None:
            await self.close(code=4404)
            return

        await self.channel_layer.group_add(self.channel_group, self.channel_name)
        await self.accept()

        # Send current status + recent backlog so a fresh client is in sync.
        await self.send_json("status", {
            "status": group.status,
            "topic": group.topic,
            "name": group.name,
            "speed_ms": group.speed_ms,
            "turn_mode": group.turn_mode,
            "running": engine.is_running(self.group_id),
        })
        await self.send_json("history", {"messages": await self._recent_messages()})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.channel_group, self.channel_name)

    # ── Inbound from the browser ─────────────────────────────────────────
    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            await self.send_json("error", {"message": "Invalid JSON."})
            return

        action = payload.get("action")
        gid = self.group_id

        if action == "start":
            await engine.start(gid)
            await self.broadcast_status()
        elif action == "pause":
            await engine.pause(gid)
            await self.broadcast_status()
        elif action == "stop":
            await engine.stop(gid)
            await self.broadcast_status()
        elif action == "human_message":
            content = (payload.get("content") or "").strip()
            if content:
                await engine.inject_human_message(gid, content)
        elif action == "priority_floor":
            await engine.set_priority_floor(
                gid, payload["agent_id"], bool(payload.get("on", True))
            )
        elif action == "mute":
            await engine.set_muted(
                gid, payload["agent_id"], bool(payload.get("muted", True))
            )
        elif action == "set_speed":
            await engine.set_speed(gid, int(payload.get("speed_ms", 3000)))
        elif action == "set_topic":
            topic = (payload.get("topic") or "").strip()
            if topic:
                await engine.set_topic(gid, topic)
        else:
            await self.send_json("error", {"message": f"Unknown action: {action}"})

    # ── Channel-layer fan-out (engine -> all clients) ────────────────────
    async def sim_event(self, message):
        """Handler for {"type": "sim.event", ...} broadcasts from the engine."""
        await self.send(text_data=json.dumps(
            {"event": message["event"], "data": message["data"]}
        ))

    # ── Helpers ──────────────────────────────────────────────────────────
    async def broadcast_status(self):
        group = await self._get_group()
        if group:
            await self.channel_layer.group_send(
                self.channel_group,
                {
                    "type": "sim.event",
                    "event": "status",
                    "data": {
                        "status": group.status,
                        "running": engine.is_running(self.group_id),
                    },
                },
            )

    async def send_json(self, event, data):
        await self.send(text_data=json.dumps({"event": event, "data": data}))

    @sync_to_async
    def _get_group(self):
        return Group.objects.filter(id=self.group_id).first()

    @sync_to_async
    def _recent_messages(self, limit=50):
        qs = (
            Message.objects.filter(
                group_id=self.group_id, kind=Message.Kind.CHAT
            )
            .select_related("agent")
            .order_by("-created_at")[:limit]
        )
        out = []
        for m in reversed(list(qs)):
            out.append({
                "id": str(m.id),
                "agent_id": str(m.agent_id) if m.agent_id else None,
                "agent_name": m.agent.name if m.agent else None,
                "agent_color": m.agent.avatar_color if m.agent else None,
                "agent_emoji": m.agent.avatar_emoji if m.agent else None,
                "role": m.role,
                "content": m.content,
                "tokens_used": m.tokens_used,
                "response_ms": m.response_ms,
                "created_at": m.created_at.isoformat(),
            })
        return out

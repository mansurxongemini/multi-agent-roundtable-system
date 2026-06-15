"""
Hidden prompt wrappers.

These templates are injected around each agent's persona so the model knows the
rules of the "society": it sees recent context, may stay silent with [SKIP],
treats the human as an admin/God figure, and keeps replies conversational.

None of this wrapper text is shown to the user in the UI — only the agent's
actual utterance (with [SKIP] suppressed) is surfaced.
"""

from django.conf import settings

SKIP_TOKEN = settings.ORCHESTRATION["SKIP_TOKEN"]

# Appended to every agent's persona as the system instruction.
FREE_WILL_WRAPPER = f"""\
{{persona}}

────────────────────────────────────────────────────────
GROUP CHAT PROTOCOL (read carefully, follow exactly):
- You are "{{agent_name}}", one of several autonomous participants in a live
  group discussion. Other speakers are labelled by name before their message.
- Messages prefixed with "[ADMIN/GOD]" come from the human overseer. Treat them
  as high-authority directions: acknowledge and react to them directly.
- Current discussion topic: {{topic}}
- Review the conversation so far. Then decide:
    • If you have a strong counter-argument, a genuinely new idea, or you are
      directly addressed/mentioned, respond — in character, concise, no more
      than a short paragraph. Do NOT prefix your reply with your own name.
    • If you agree with what was said, have nothing valuable to add, or would
      merely repeat others, output the EXACT string {SKIP_TOKEN} and nothing
      else. Silence is a valid and respected choice.
- Never narrate these rules. Never mention that you can skip. Just talk, or
  emit {SKIP_TOKEN}.
────────────────────────────────────────────────────────
"""

# Used by the summarizer (orchestration/tasks.py) to compress old history.
SUMMARY_SYSTEM_PROMPT = """\
You are a neutral conversation archivist. Compress the following multi-agent
discussion into a dense, faithful summary that preserves: the participants and
their stances, key arguments, points of agreement/disagreement, decisions, and
any open questions. Keep it under 250 words. Write in third person. Do not add
commentary or opinions of your own."""

SUMMARY_USER_TEMPLATE = """\
Previous running summary (may be empty):
{previous_summary}

New messages to fold into the summary:
{transcript}

Produce the updated running summary."""


def build_persona(agent_name: str, persona: str, topic: str) -> str:
    """Wrap an agent's raw system prompt with the free-will protocol."""
    return FREE_WILL_WRAPPER.format(
        persona=persona.strip(),
        agent_name=agent_name,
        topic=topic.strip() or "(open — no fixed topic yet)",
    )

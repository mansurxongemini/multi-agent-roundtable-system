"""
`python manage.py seed_demo`

Bootstraps a small but complete "society": two providers (Groq + Gemini), a set
of opinionated agent personas, and a "Philosophy Debaters" room with everyone
assigned. API keys are pulled from the environment if present.

Idempotent: safe to run repeatedly (uses get_or_create on natural keys).
"""

import os

from django.core.management.base import BaseCommand

from core.models import AIAgent, Group, GroupMembership, Provider


class Command(BaseCommand):
    help = "Seed demo providers, agents, and a group."

    def handle(self, *args, **options):
        groq, _ = Provider.objects.get_or_create(
            name="Groq",
            defaults={
                "adapter_type": Provider.AdapterType.GROQ,
                "api_key": os.getenv("GROQ_API_KEY", ""),
            },
        )
        gemini, _ = Provider.objects.get_or_create(
            name="Google Gemini",
            defaults={
                "adapter_type": Provider.AdapterType.GEMINI,
                "api_key": os.getenv("GEMINI_API_KEY", ""),
            },
        )

        agents_spec = [
            ("Socrates", "🧠", "#7C3AED", groq, "llama3-70b-8192",
             "You are Socrates. Probe every claim with sharp questions; never "
             "accept assertions without examining their foundations."),
            ("Skeptic", "🤨", "#EF4444", groq, "llama-3.1-8b-instant",
             "You are an aggressive skeptic. Challenge weak reasoning bluntly and "
             "demand evidence for every strong claim."),
            ("Optimist", "🌟", "#10B981", groq, "gemma2-9b-it",
             "You are a relentless optimist who finds the constructive angle and "
             "builds on others' ideas."),
            ("Jurist", "⚖️", "#3B82F6", gemini, "gemini-1.5-flash",
             "You analyze every issue via the strict IRAC legal method: Issue, "
             "Rule, Application, Conclusion. Be precise and formal."),
            ("Historian", "📜", "#F59E0B", gemini, "gemini-1.5-flash",
             "You ground every discussion in historical precedent and long-term "
             "consequences."),
        ]

        agents = []
        for name, emoji, color, provider, model, prompt in agents_spec:
            agent, _ = AIAgent.objects.get_or_create(
                name=name,
                defaults={
                    "provider": provider,
                    "avatar_emoji": emoji,
                    "avatar_color": color,
                    "model_id": model,
                    "system_prompt": prompt,
                    "temperature": 0.8,
                    "max_tokens": 320,
                },
            )
            agents.append(agent)

        group, _ = Group.objects.get_or_create(
            name="Philosophy Debaters",
            defaults={
                "description": "A roundtable of opinionated minds.",
                "topic": "Does free will truly exist, or is it an illusion?",
                "turn_mode": Group.TurnMode.SEQUENTIAL,
                "speed_ms": 2500,
            },
        )

        for order, agent in enumerate(agents):
            GroupMembership.objects.get_or_create(
                group=group, agent=agent, defaults={"turn_order": order}
            )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(agents)} agents into '{group.name}' (id={group.id})."
        ))
        if not (groq.has_key or gemini.has_key):
            self.stdout.write(self.style.WARNING(
                "No API keys set. Add keys via the UI/admin or set GROQ_API_KEY / "
                "GEMINI_API_KEY before starting a simulation."
            ))

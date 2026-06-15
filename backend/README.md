# AI Society Simulation

A real-time, multi-agent ecosystem where autonomous LLM agents (Groq, Gemini,
OpenAI, Anthropic, or any OpenAI-compatible endpoint) converse inside groups
while a human **"God / Admin"** monitors, intervenes, and controls the flow.

Built with **Django + Django Channels (WebSockets) + PostgreSQL + Redis + Celery**
and a dependency-free, hyper-minimalist `#000000` frontend.

---

## 1. Architecture at a glance

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Browser (God/Admin)  ──REST──▶  Django REST API     (providers/agents/…)  │
│        │                                                                   │
│        └────WebSocket────▶  GroupConsumer ──▶ SimulationEngine (asyncio)    │
│                                   ▲                    │                    │
│                                   │            per-group autonomous loop    │
│                          Channels (Redis)  ◀──broadcast events──┘           │
│                                                        │                    │
│                                   ┌────────────────────┼─────────────┐      │
│                                   ▼                    ▼             ▼      │
│                            AIRouter→Adapters     MemoryManager   Celery     │
│                            (Groq/Gemini/…)    (sliding window)  (summaries) │
│                                   │                    │             │      │
│                                   └──────── PostgreSQL ◀────────────┘       │
└──────────────────────────────────────────────────────────────────────────┘
```

### Directory structure

```
backend/
├── manage.py
├── requirements.txt
├── Dockerfile · docker-compose.yml · .env.example
├── aisociety/                 # project config
│   ├── settings.py            # Channels + Postgres + Redis + Celery + encryption
│   ├── asgi.py                # HTTP + WebSocket routing
│   ├── celery.py              # background task app
│   └── urls.py
├── core/                      # data layer
│   ├── models.py              # Provider, AIAgent, Group, GroupMembership, Message
│   ├── fields.py              # EncryptedTextField (Fernet) for API keys
│   ├── admin.py
│   └── management/commands/seed_demo.py
├── providers/                 # adapter pattern (pluggable LLM vendors)
│   ├── base.py                # BaseAIAdapter + CompletionResult
│   ├── openai_compatible.py   # Groq / OpenAI / Custom
│   ├── gemini.py              # Google Gemini
│   ├── anthropic.py           # Claude
│   └── router.py              # AIRouter factory
├── orchestration/             # the realtime engine
│   ├── prompts.py             # free-will wrapper + summary prompts
│   ├── memory.py              # sliding window + context builder
│   ├── turn_manager.py        # who speaks next (+ priority floor)
│   ├── engine.py              # autonomous loop + God-Mode controls
│   ├── tasks.py               # Celery rolling-summary compression
│   ├── consumers.py           # WebSocket consumer
│   └── routing.py
├── api/                       # DRF: serializers, views, urls
├── templates/index.html       # SPA shell
└── frontend/                  # style.css + app.js (vanilla, minimalist)
```

---

## 2. Feature mapping

| Requirement | Where it lives |
|---|---|
| **Dynamic API & Provider Hub** | `core.Provider` + `providers/router.py` (adapter pattern); keys encrypted via `core/fields.py`; managed in the Providers modal |
| **Agent persona management** | `core.AIAgent` (name, color/emoji, model, system prompt, temperature, max tokens) |
| **Community / Group rooms** | `core.Group` + `core.GroupMembership`; multiple groups run concurrent loops |
| **Free will + orchestration** | `orchestration/engine.py` loop; `prompts.FREE_WILL_WRAPPER` instructs agents to emit `[SKIP]`; skipped output is suppressed and never persisted |
| **God Mode controls** | Engine: `set_muted`, `set_priority_floor`, `inject_human_message`, `pause`; driven from the agent cards + composer |
| **Infinite memory** | `orchestration/memory.py` (sliding window) + `orchestration/tasks.compress_history` (rolling summary via Celery) |

---

## 3. Quick start (Docker — recommended)

```bash
cd backend
cp .env.example .env

# Generate the encryption key required for API-key storage:
python -c "from cryptography.fernet import Fernet; print('FERNET_KEY='+Fernet.generate_key().decode())"
# → paste the line into .env

docker compose up --build
# App:   http://localhost:8000
# Admin: http://localhost:8000/admin/   (create a superuser first, see below)
```

Seed a demo society and create an admin user:

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo
```

## 4. Quick start (local, without Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in FERNET_KEY, Postgres, Redis

# Requires a running PostgreSQL + Redis (e.g. via `docker compose up db redis`).
python manage.py makemigrations core
python manage.py migrate
python manage.py seed_demo

# ASGI server (HTTP + WebSockets) — NOT `runserver` for production.
daphne -b 0.0.0.0 -p 8000 aisociety.asgi:application

# In a second terminal: the summarization worker.
celery -A aisociety worker -l info
```

Then open `http://localhost:8000`, add your API keys in **Providers & Keys**,
open a room, and press **Start**.

---

## 5. Usage flow

1. **Providers & Keys** → add Groq / Gemini / OpenAI keys (stored encrypted).
2. **Agents** → create personas (model id + system prompt + temperature).
3. **Rooms** (`+`) → create a group, set topic + turn mode + speed.
4. Open the room → **Assign agent** tiles to populate the roster.
5. **Start** → the autonomous loop runs; agents speak or `[SKIP]` in turn.
6. **God Mode** during a live run:
   - **Mute** / **Unmute** an agent (top of each card).
   - **Floor** — force an agent to speak next, jumping the queue.
   - **Inject** — type as `ADMIN / GOD`; agents perceive it as authoritative.
   - **Pause / Stop** the whole room from the top bar.

---

## 6. Provider integration examples

**Groq** (OpenAI-compatible) — `providers/openai_compatible.py`:

```http
POST https://api.groq.com/openai/v1/chat/completions
Authorization: Bearer <GROQ_API_KEY>
{
  "model": "llama3-70b-8192",
  "messages": [
    {"role": "system", "content": "<persona + free-will wrapper>"},
    {"role": "user",   "content": "Socrates: But what is justice?"}
  ],
  "temperature": 0.8, "max_tokens": 320
}
```

**Gemini** — `providers/gemini.py`:

```http
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=<KEY>
{
  "system_instruction": {"parts": [{"text": "<persona + wrapper>"}]},
  "contents": [{"role": "user", "parts": [{"text": "Socrates: But what is justice?"}]}],
  "generationConfig": {"temperature": 0.8, "maxOutputTokens": 320}
}
```

Adding a new vendor = write one `BaseAIAdapter` subclass and register it in
`providers/router.py::_REGISTRY`.

---

## 7. Notes & production hardening

- **Security**: API keys are encrypted at rest (Fernet) and are *write-only* in
  the API — the frontend can set but never read them. Add real authentication
  (DRF auth + per-user scoping) before exposing publicly.
- **Scaling the loops**: the engine hosts one `asyncio` loop per running group
  inside the ASGI process. For multi-process / multi-node deployments, move loop
  ownership to a dedicated worker keyed by group and coordinate via Redis locks.
- **Rate limits**: provider calls retry with exponential backoff on HTTP 429;
  after `ORCHESTRATION.MAX_RETRIES` the agent is skipped for that turn so the
  loop never crashes.
- **Memory**: once un-summarised history exceeds
  `ORCHESTRATION.SUMMARY_TOKEN_THRESHOLD`, a Celery task folds old messages into
  `Group.rolling_summary`; agents always receive `summary + last N messages`.

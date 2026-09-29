# 🤖 Multi-Agent AI Roundtable Orchestration Platform

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Django 5.0](https://img.shields.io/badge/Django-5.0-092E20.svg?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Django Channels](https://img.shields.io/badge/Django_Channels-WebSocket-2BA977.svg)](https://channels.readthedocs.io/)
[![Redis](https://img.shields.io/badge/Redis-PubSub-DC382D.svg?logo=redis&logoColor=white)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-Distributed_Tasks-37814A.svg?logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A real-time, multi-agent conversational ecosystem and simulation platform where autonomous frontier LLM agents (**OpenAI, Google Gemini, Anthropic Claude, Groq**, and any custom OpenAI-compatible endpoint) converse dynamically in collaborative roundtables, while a human **"God / Moderator"** monitors, guides, intervenes, and controls the flow in real time.

Built with **Django, Django Channels (WebSockets), Redis Pub/Sub, Celery rolling context memory**, and a high-performance minimalist `#000000` single-page frontend.

---

## 🏛️ System Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Browser (God / Moderator) ──REST──▶  Django REST API (Providers/Agents) │
│        │                                                                 │
│        └────WebSocket────▶  GroupConsumer ──▶ SimulationEngine (asyncio)  │
│                                   ▲                    │                 │
│                                   │          Concurrent Autonomous Loop  │
│                          Channels (Redis)  ◀──Broadcast Events──┘        │
│                                                        │                 │
│                                   ┌────────────────────┼───────────┐     │
│                                   ▼                    ▼           ▼     │
│                            AIRouter→Adapters     MemoryManager   Celery  │
│                         (OpenAI/Gemini/Claude) (Sliding Window) (Summary)│
│                                   │                    │           │     │
│                                   └────────  Database (SQLite/PG) ◀┘     │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 🌟 Key Capabilities

### 1. Multi-Provider LLM Adapter Layer
Pluggable adapter design (`providers/`) unifying diverse AI vendors under an asynchronous interface:
- **OpenAI**: GPT-4o, GPT-4o-mini, o1/o3 reasoning models.
- **Anthropic**: Claude 3.5 Sonnet, Claude 3 Opus, Claude 3.5 Haiku.
- **Google Gemini**: Gemini 2.5 Pro, Flash via official SDK endpoints.
- **Groq & Custom Endpoints**: Ultra-low-latency LLaMA 3.3 70B, Mistral, Local vLLM/Ollama servers.
- **Fernet Key Encryption**: API keys are securely encrypted at rest using AES-128-CBC (`core/fields.py`).

### 2. Autonomous Conversational Engine & Free-Will Protocol
- **Autonomous Turn Management**: The orchestrator evaluates context and invites active agents to speak based on personality, expertise, and dynamic priority floors.
- **Free-Will `[SKIP]` Wrapper**: Agents can autonomously decline to speak (`[SKIP]`) if the message is outside their domain or they agree with previous statements, avoiding unnatural conversational chatter.
- **Roundtable Consensus**: Facilitates multi-agent debate, code review, peer critique, and collaborative reasoning.

### 3. God-Mode Moderator Controls
- **Live Injection**: Inject moderator directives or user prompts into the round at any millisecond.
- **Dynamic Priority & Muting**: Mute runaway agents or raise the floor to force specific specialists to respond.
- **State Control**: Pause, resume, rewind, or wipe history on the fly.

### 4. Infinite Conversational Memory
- **Sliding-Window Cache**: Fast in-memory token retrieval of recent discourse.
- **Celery Rolling Summarization**: Background worker compresses historical rounds into dense executive summaries, preventing token overflow while preserving deep semantic continuity.

---

## 📂 Repository Layout

```
.
├── AI_Roundtable_Prompt.md     # Full architectural & product specifications
├── backend/
│   ├── manage.py               # Django CLI
│   ├── Dockerfile              # Container image
│   ├── docker-compose.yml      # Orchestrated backend, redis & celery
│   ├── aisociety/              # Core ASGI & Channels configuration
│   ├── core/                   # Models: Provider, AIAgent, Group, Message
│   ├── providers/              # Adapter implementations (OpenAI, Gemini, Claude)
│   ├── orchestration/          # Engine, memory manager, turn manager, WebSocket consumers
│   ├── api/                    # REST API endpoints & serializers
│   ├── templates/              # SPA shell
│   └── frontend/               # Vanilla CSS/JS client
```

---

## 🚀 Quickstart Guide

### Option 1: Docker Compose (Recommended)

```bash
cd backend
cp .env.example .env
# Add your SECRET_KEY and ENCRYPTION_KEY in .env

docker-compose up --build
```
The application will be live at `http://localhost:8000`.

### Option 2: Local Development Setup

```bash
# 1. Clone repository
git clone https://github.com/mansurxongemini/multi-agent-roundtable-system.git
cd multi-agent-roundtable-system/backend

# 2. Virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Environment configuration
cp .env.example .env

# 4. Migrate database & seed demo agents
python manage.py migrate
python manage.py seed_demo

# 5. Run ASGI server
daphne -b 0.0.0.0 -p 8000 aisociety.asgi:application
```

---

## 🤝 Open Source & Contributions

Contributions, feature proposals, and provider adapters are welcome! Please open an issue or pull request.

**License**: MIT License. Built for frontier multi-agent research and collaborative AI applications.

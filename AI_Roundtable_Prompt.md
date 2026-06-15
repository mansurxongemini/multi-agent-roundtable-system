# 🤖 AI ROUNDTABLE — To'liq Dastur Spesifikatsiyasi

> **Maqsad:** Bir nechta AI agentlar (Groq, Gemini, OpenAI, Anthropic va boshqalar) o'zaro suhbat quradigan, foydalanuvchi ham ishtirok etadigan, real-time, zamonaviy veb-ilova yaratish.

---

## 1. LOYIHA UMUMIY TAVSIFI

### Nima quramiz?

Brauzerda ishlaydigan **"AI Davra Suhbati"** platformasi. Bu platformada:
- Har xil AI provayderlardan kelgan bir nechta agent "shaxsiyat" sifatida suhbatlashadi
- Foydalanuvchi moderator yoki ishtirokchi sifatida qo'shilishi mumkin
- Suhbat real-time websocket orqali oqadi
- Har bir AI agentning o'z ismi, avatari, roli va xususiyati bor
- Sistema cheksiz davom eta oladi (doimiy suhbat)

---

## 2. TEXNIK STEK

### Backend
```
Runtime:    Python 3.11+ yoki Node.js 20+
Framework:  FastAPI (Python) yoki Express + Socket.io (Node.js)
WebSocket:  FastAPI WebSocket yoki Socket.io
Database:   SQLite (dev) / PostgreSQL (prod)
ORM:        SQLAlchemy (Python) yoki Prisma (Node.js)
Queue:      Asyncio (Python) yoki Bull (Node.js)
```

### Frontend
```
Stack:      Vanilla HTML/CSS/JS yoki React 18 + Vite
Styling:    CSS Custom Properties + Tailwind CSS (ixtiyoriy)
Real-time:  native WebSocket yoki socket.io-client
Storage:    IndexedDB (Dexie.js) + localStorage
Charts:     Chart.js yoki Recharts
Icons:      Lucide Icons yoki Tabler Icons
```

### AI Provayder Integratsiya
```
Groq:       @groq-sdk (npm) yoki groq (pip)
Gemini:     @google/generative-ai (npm) yoki google-generativeai (pip)
OpenAI:     openai (npm yoki pip)
Anthropic:  @anthropic-ai/sdk yoki anthropic (pip)
Custom:     Har qanday OpenAI-compatible endpoint
```

---

## 3. MA'LUMOTLAR BAZASI SXEMASI

```sql
-- Provayderlar jadvali
CREATE TABLE providers (
    id          TEXT PRIMARY KEY,         -- "groq", "gemini", "openai", custom UUID
    name        TEXT NOT NULL,            -- "Groq", "Google Gemini"
    base_url    TEXT NOT NULL,            -- API endpoint
    api_key     TEXT,                     -- Shifrlangan
    is_active   BOOLEAN DEFAULT true,
    created_at  DATETIME DEFAULT NOW()
);

-- AI Agentlar jadvali
CREATE TABLE agents (
    id              TEXT PRIMARY KEY,     -- UUID
    provider_id     TEXT REFERENCES providers(id),
    name            TEXT NOT NULL,        -- "Sokrat", "Einstein", "Zulfiya"
    model           TEXT NOT NULL,        -- "llama-3.3-70b", "gemini-2.0-flash"
    avatar_color    TEXT,                 -- "#7C3AED"
    avatar_emoji    TEXT,                 -- "🧠", "⚡", "🌟"
    system_prompt   TEXT,                 -- Shaxsiyat / rol tavsifi
    temperature     REAL DEFAULT 0.7,     -- 0.0 — 2.0
    max_tokens      INTEGER DEFAULT 500,
    is_active       BOOLEAN DEFAULT true,
    turn_order      INTEGER,              -- Navbat tartibi
    created_at      DATETIME DEFAULT NOW()
);

-- Suhbatlar jadvali
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    topic       TEXT,                     -- Joriy muhokama mavzusi
    status      TEXT DEFAULT 'paused',    -- 'running', 'paused', 'stopped'
    speed_ms    INTEGER DEFAULT 3000,     -- Xabarlar orasidagi interval (ms)
    turn_mode   TEXT DEFAULT 'sequential',-- 'sequential', 'random', 'weighted'
    created_at  DATETIME DEFAULT NOW()
);

-- Xabarlar jadvali
CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    agent_id        TEXT REFERENCES agents(id),  -- NULL = foydalanuvchi
    role            TEXT NOT NULL,               -- 'agent', 'user', 'system'
    content         TEXT NOT NULL,
    tokens_used     INTEGER,
    response_ms     INTEGER,             -- Javob vaqti (millisekund)
    skipped         BOOLEAN DEFAULT false, -- Agent javob bermadi
    mentions        TEXT,                -- JSON: ["agent_id1", "agent_id2"]
    created_at      DATETIME DEFAULT NOW()
);
```

---

## 4. BACKEND ARXITEKTURASI

### 4.1 API Endpointlar (REST)

```
# Provider Management
GET    /api/providers                  -- Barcha provayderlarni olish
POST   /api/providers                  -- Yangi provayder qo'shish
PUT    /api/providers/{id}             -- Provayderni yangilash
DELETE /api/providers/{id}             -- O'chirish
GET    /api/providers/{id}/models      -- Mavjud modellar ro'yxati

# Agent Management
GET    /api/agents                     -- Barcha agentlar
POST   /api/agents                     -- Yangi agent yaratish
PUT    /api/agents/{id}                -- Agentni tahrirlash
DELETE /api/agents/{id}                -- O'chirish
POST   /api/agents/{id}/test           -- Agentni sinab ko'rish

# Conversation Management
GET    /api/conversations              -- Suhbatlar ro'yxati
POST   /api/conversations              -- Yangi suhbat
GET    /api/conversations/{id}         -- Suhbat ma'lumotlari
GET    /api/conversations/{id}/messages-- Xabarlar (pagination bilan)
PUT    /api/conversations/{id}/status  -- start/pause/stop
PUT    /api/conversations/{id}/topic   -- Mavzuni o'zgartirish
GET    /api/conversations/{id}/export  -- JSON/TXT/MD eksport

# Analytics
GET    /api/analytics/tokens           -- Token sarfi statistikasi
GET    /api/analytics/activity         -- Agent faollik darajasi
GET    /api/analytics/response-times   -- Javob tezligi
```

### 4.2 WebSocket Events

```
# Serverdan Clientga (emit)
ws:message_new          -- Yangi xabar keldi
ws:agent_thinking       -- Agent javob yozmoqda (typing indicator)
ws:agent_skipped        -- Agent bu safar javob bermadi
ws:conversation_started -- Suhbat boshlandi
ws:conversation_paused  -- Pauzaga olindi
ws:conversation_stopped -- To'xtatildi
ws:topic_changed        -- Mavzu o'zgardi
ws:agent_added          -- Yangi agent qo'shildi
ws:agent_removed        -- Agent o'chirildi
ws:error                -- Xato yuz berdi

# Clientdan Serverga (on)
ws:user_message         -- Foydalanuvchi xabar yubordi
ws:pause_request        -- Pause so'rovi
ws:resume_request       -- Davom ettirish so'rovi
ws:topic_inject         -- Yangi mavzu kiritish
ws:speed_change         -- Tezlikni o'zgartirish
ws:skip_current         -- Joriy agentni o'tkazib yuborish
```

### 4.3 Turn Manager Algoritmi

```python
class TurnManager:
    """
    Navbat boshqaruvchisi — kim keyingi gapiradi?
    """
    
    modes = {
        "sequential": # A1 → A2 → A3 → B1 → B2 → A1...
            # Tartibli aylanma navbat
            
        "random": # Tasodifiy tanlash, lekin ketma-ket takrorlanmaslik
            # Oxirgi 3 agentni istisno qilish
            
        "weighted": # Ko'p gaplashganlar kamroq, kamroq gaplashganlar ko'proq
            # turn_count inversiga proporsional ehtimollik
            
        "reactive": # Xabardagi @mention bo'lsa, o'sha agent javob beradi
            # Mention yo'q bo'lsa weighted mode
    }
    
    def should_skip(self, agent, context) -> bool:
        """
        Agent bu safar javob berishi kerakmi?
        - temperature va creativity asosida 20% ehtimollik bilan skip
        - Agar mavzu agent ixtisosligidan tashqarida bo'lsa 40% skip
        - Agar agent allaqachon 3 marta ketma-ket gapirgan bo'lsa skip
        """
```

### 4.4 AI Provayder Adapter Pattern

```python
class BaseAIAdapter:
    """Barcha provayderlar uchun umumiy interfeys"""
    
    async def generate(
        self,
        messages: List[dict],
        system_prompt: str,
        temperature: float,
        max_tokens: int,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        raise NotImplementedError


class GroqAdapter(BaseAIAdapter):
    """Groq uchun adapter"""
    # llama-3.3-70b, mixtral-8x7b, gemma-7b va boshqalar
    
class GeminiAdapter(BaseAIAdapter):
    """Google Gemini uchun adapter"""
    # gemini-2.0-flash, gemini-1.5-pro va boshqalar

class OpenAIAdapter(BaseAIAdapter):
    """OpenAI uchun adapter"""
    # gpt-4o, gpt-4o-mini va boshqalar

class AnthropicAdapter(BaseAIAdapter):
    """Anthropic Claude uchun adapter"""
    # claude-3-5-sonnet, claude-3-haiku va boshqalar

class CustomAdapter(BaseAIAdapter):
    """Har qanday OpenAI-compatible endpoint uchun"""
    # Ollama, Together AI, Perplexity, LM Studio va boshqalar


class AIRouter:
    """Provider ID ga qarab to'g'ri adapterni tanlaydi"""
    
    adapters = {
        "groq": GroqAdapter,
        "gemini": GeminiAdapter,
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter,
        # Dinamik: yangi provider qo'shilganda ro'yxatga kiritiladi
    }
    
    def get_adapter(self, provider_id: str) -> BaseAIAdapter:
        ...
```

### 4.5 Memory Manager — Kontekst Boshqaruvi

```python
class MemoryManager:
    """
    Har bir agent o'z xotirasiga ega:
    1. Global context: Barcha agentlar ko'radigan umumiy suhbat (oxirgi N xabar)
    2. Personal memory: Har bir agent o'zi aytgan narsalar
    3. Topic memory: Joriy mavzuga oid asosiy faktlar
    
    Muammo: Token limiti
    Yechim: Sliding window + summarization
    - Oxirgi 20 xabarni to'liq saqlash
    - Undan oldingilarni qisqacha xulosa sifatida berish
    """
    
    def build_context(
        self,
        agent_id: str,
        conversation_id: str,
        window_size: int = 20
    ) -> List[dict]:
        """
        Agent uchun kontekst xabarlar to'plamini qaytaradi.
        Format: [{"role": "user/assistant", "content": "..."}]
        """
```

---

## 5. FRONTEND ARXITEKTURASI

### 5.1 Sahifa Tuzilmasi (Single Page Application)

```
App
├── Sidebar (chapda, yig'iladigan)
│   ├── SidebarHeader (Logo + ism)
│   ├── ConversationList (o'tgan suhbatlar)
│   ├── AgentList (faol agentlar ro'yxati)
│   └── SidebarFooter (Sozlamalar, Eksport)
│
├── MainPanel (o'rtada, asosiy)
│   ├── TopBar
│   │   ├── ConversationTitle (tahrir qilish mumkin)
│   │   ├── TopicBadge (joriy mavzu)
│   │   ├── StatusIndicator (running/paused)
│   │   └── ControlButtons (start/pause/stop/skip)
│   │
│   ├── AgentRow (yuqori qism — agent kartalar)
│   │   ├── AgentCard × N (har bir AI uchun)
│   │   │   ├── Avatar (emoji + rang + animatsiya)
│   │   │   ├── AgentName + ModelBadge
│   │   │   ├── ProviderLogo (Groq/Gemini/...)
│   │   │   ├── TokenCounter (sarflangan tokenlar)
│   │   │   ├── ThinkingDots (javob yozayotganda)
│   │   │   └── StatusLight (green=aktiv, gray=kutish)
│   │   └── AddAgentButton
│   │
│   ├── ChatStream (asosiy qism)
│   │   └── MessageBubble × N
│   │       ├── AgentAvatar (kichik)
│   │       ├── AgentName + Timestamp
│   │       ├── MessageContent (markdown render)
│   │       ├── MentionHighlights (@agent ismlari)
│   │       ├── TokenInfo (yig'iladigan)
│   │       └── ReactionBar (👍 👎 💡 ⭐)
│   │
│   └── UserInputArea (pastda)
│       ├── MentionDropdown (@agent tanlash)
│       ├── TextArea (xabar yozish)
│       ├── CharacterCounter
│       └── SendButton + ShortcutHint (Ctrl+Enter)
│
└── RightPanel (o'ngda, yig'iladigan)
    ├── AnalyticsTab
    │   ├── MessageCountChart (kimdan nechta)
    │   ├── TokenUsageBar
    │   ├── ResponseTimeGauge
    │   └── ActivityTimeline
    │
    ├── SettingsTab
    │   ├── SpeedSlider (500ms — 10000ms)
    │   ├── TurnModeSelector
    │   ├── ContextWindowSize
    │   └── AutoSummarize toggle
    │
    └── ProvidersTab
        ├── ProviderCard × N
        │   ├── ProviderName + Logo
        │   ├── APIKeyField (masked)
        │   ├── ConnectionStatus
        │   └── ModelDropdown
        └── AddProviderForm
```

### 5.2 Agent Karta Dizayni

```css
/* Har bir AI agent uchun karta */
.agent-card {
    position: relative;
    width: 160px;
    background: var(--surface);
    border: 1.5px solid var(--border);
    border-radius: 16px;
    padding: 16px 12px;
    
    /* Aktiv holatda (javob yozayotganda) */
    &.is-thinking {
        border-color: var(--agent-color);
        box-shadow: 0 0 0 3px color-mix(in srgb, var(--agent-color) 20%, transparent);
    }
    
    /* Skip holatida */
    &.is-skipped {
        opacity: 0.5;
    }
}

.agent-avatar {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: var(--agent-color);
    font-size: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* Thinking animation */
.thinking-dots span {
    animation: pulse 1.4s ease-in-out infinite;
}
.thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
```

### 5.3 Chat Bubble Komponenti

```javascript
// Har bir xabar uchun komponent
const MessageBubble = ({ message }) => {
    const isUser = message.role === 'user';
    const agent = agentsMap[message.agent_id];
    
    // @mention larni ajratib ko'rsatish
    const renderContent = (text) => {
        return text.replace(/@(\w+)/g, (match, name) => {
            return `<span class="mention">@${name}</span>`;
        });
    };
    
    // Markdown render (marked.js orqali)
    const html = marked.parse(renderContent(message.content));
    
    return (
        <div class={`message ${isUser ? 'user-message' : 'agent-message'}`}>
            <div class="message-header">
                <span class="agent-avatar" style={{ background: agent?.color }}>
                    {agent?.emoji}
                </span>
                <span class="agent-name">{agent?.name ?? 'Siz'}</span>
                <span class="model-badge">{agent?.model}</span>
                <span class="timestamp">{formatTime(message.created_at)}</span>
                {message.skipped && <span class="skip-badge">⏭ o'tkazdi</span>}
            </div>
            <div class="message-body" dangerouslySetInnerHTML={{ __html: html }} />
            <div class="message-footer">
                <span class="token-count">🪙 {message.tokens_used}</span>
                <span class="response-time">⚡ {message.response_ms}ms</span>
                <div class="reactions">
                    {['👍', '👎', '💡', '⭐', '🔥'].map(r => (
                        <button onClick={() => react(message.id, r)}>{r}</button>
                    ))}
                </div>
            </div>
        </div>
    );
};
```

---

## 6. ASOSIY FUNKSIYALAR (BATAFSIL)

### F1 — Davra Suhbati (Round Table)

```
Qanday ishlaydi:
1. Foydalanuvchi "Start" tugmasini bosadi
2. Turn Manager navbatni aniqlaydi (kim birinchi?)
3. AI Router — agent provayderini topadi
4. Memory Manager — kontekstni to'playdi (oxirgi N xabar)
5. Adapter — API ga so'rov yuboradi (streaming)
6. Xabar WebSocket orqali frontendga keladi (real-time oqim)
7. Xabar DB ga saqlanadi
8. Keyingi agent navbati boshlanadi (speed_ms kutib)
9. Cheksiz davom etadi

Alohida qoidalar:
- Agar API xatosi bo'lsa: 3 marta qayta urinish, keyin skip
- Agar agent kontekstni yo'qotsa: Memory Manager xulosa beradi
- Agar mavzu uzoq vaqtdan beri o'zgarmagan bo'lsa: Topic nudge yuborish
```

### F2 — Ko'p Agentli Tizim

```
Groq tomonida misol (5 agent):
┌─────────────────────────────────────────┐
│  "Sokrat"     - llama-3.3-70b           │
│  → System: "Sen faylasuf Sokrat sifatida│
│    savollar berib fikr yuritasan..."     │
│                                          │
│  "Hacker"     - mixtral-8x7b-32768      │
│  → System: "Sen kiberbezopaslik mutaxassisi│
│    sifatida texnik jihatlarni tahlil..."  │
│                                          │
│  "Skeptik"    - llama-3.1-8b-instant    │
│  → System: "Sen hamma fikrga shubha...  │
│                                          │
│  "Optimist"   - gemma2-9b-it            │
│  → System: "Sen ijobiy nuqtai nazardan..│
│                                          │
│  "Faktolog"   - llama-3.3-70b           │
│  → System: "Sen faqat isbotlangan fakt..│
└─────────────────────────────────────────┘

Gemini tomonida misol (6 agent):
┌─────────────────────────────────────────┐
│  "Jurist"     - gemini-2.0-flash        │
│  "Iqtisodchi" - gemini-1.5-pro          │
│  "Shoir"      - gemini-2.0-flash        │
│  "Muhandis"   - gemini-1.5-flash        │
│  "Psixolog"   - gemini-1.5-pro          │
│  "Tarixchi"   - gemini-2.0-flash        │
└─────────────────────────────────────────┘
```

### F3 — Foydalanuvchi Ishtiroki

```
Foydalanuvchi qila oladigan narsalar:
├── Xabar yozish (plain text yoki markdown)
├── @mention qilish → "@Sokrat sen bu haqda nima deb o'ylaysan?"
├── AI ni to'xtatib, o'zi gapirish
├── Mavzu o'zgartirish → "endi aytinglar, [yangi mavzu]"
├── Specific agentga savol berish
├── Barcha agentga bir vaqtda murojaat → "@all ..."
├── Agentni susaytirish/faollashtirish (agent sozlamalari)
└── "Davom et" buyrug'i bilan suhbatni yangi yo'nalishga burish

Foydalanuvchi xabari barcha agentlarga KONTEKST sifatida ko'rinadi.
Agentlar foydalanuvchini "@User" deb ataydi va unga murojaat qiladi.
```

### F4 — Provider Va Model Qo'shish

```
Yangi Provider qo'shish jarayoni:

1. "+" tugmasini bosish → Modal oynasi ochiladi
2. Provider tanlash:
   ┌─────────────────────────────────┐
   │ [Groq] [Gemini] [OpenAI] [...]  │
   │ [Anthropic] [Ollama] [Custom]   │
   └─────────────────────────────────┘

3. Tanlangandan keyin:
   - API Key (majburiy)
   - Base URL (Custom uchun)
   - Ulanishni sinash → "✅ Ulandi! 12 ta model topildi"

4. Model tanlash → model dropdown avtomatik to'ladi

5. Agent yaratish:
   ┌─────────────────────────────────┐
   │ Ism:           [Sokrat       ] │
   │ Emoji/Avatar:  [🧠            ] │
   │ Rang:          [🎨 #7C3AED   ] │
   │ Model:         [dropdown     ] │
   │ Temperature:   [━━━●━━━] 0.7  │
   │ Max tokens:    [500           ] │
   │ System prompt: [textarea      ] │
   │ Navbat tartibi:[3             ] │
   └─────────────────────────────────┘

6. "Qo'shish" → Agent suhbatga qo'shiladi
```

### F5 — Doimiy Suhbat (Continuous Conversation)

```
Mexanizm:

LOOP:
  1. Aktiv agentlar ro'yxatini ol
  2. Turn Manager → keyingi agentni tanlash
  3. Kontekstni build qilish (sliding window)
  4. API ga so'rov yuborish
  5. Streaming javobni frontendga uzatish
  6. Xabarni DBga saqlash
  7. speed_ms kutish
  8. GOTO 1

Xato ishlovi:
  - Rate limit → exponential backoff (1s → 2s → 4s → 8s)
  - Network error → 3 ta retry, keyin agent skip
  - Invalid response → kontekstni qayta qurib, yana urinish
  - API key expired → Agent deactivate, foydalanuvchini ogohlantirish
  
Auto-topic refresh (ixtiyoriy):
  - Agar 10 xabardan beri mavzu evolyusiyasi bo'lmasa
  - Sistem: "Mavzuni yangilash vaqti keldi — yangi burchak tanlang"
  - LLM uchun: suhbatni tahlil qilib yangi savol generatsiya
```

---

## 7. KENGAYTIRILGAN FUNKSIYALAR (TAVSIYALAR)

### F6 — Agent Shaxsiyat Tizimi (Personality Engine)

```
Har bir agent uchun qo'shimcha parametrlar:

personality:
  aggressiveness: 0.0 — 1.0  # Bahslashish qanchalik qattiq?
  verbosity: 0.0 — 1.0        # Qisqa yoki uzun javoblar?
  curiosity: 0.0 — 1.0        # Qanchali savol beradi?
  agreement_bias: -1.0 — 1.0  # Kelishish yoki qarshi bo'lishga moyillik
  
  example: Sokrat
    aggressiveness: 0.3
    verbosity: 0.6
    curiosity: 0.95   # Ko'p savol beradi
    agreement_bias: -0.5  # Ko'proq qarshi fikr bildiradi
```

### F7 — Kelishuv/Ziddiyat Vizualizatsiyasi (Consensus Map)

```
Real-time grafik:
- X-o'qi: Mavzu bo'yicha pozitsiya (-1: qarshi, +1: tarafdor)
- Y-o'qi: Ishonch darajasi
- Har bir agent nuqta sifatida ko'rsatiladi
- Xabar yozilganda nuqta harakat qiladi (animatsiya)

Algoritm:
1. Har bir xabarni sentiment analysis qilish (tiny LLM orqali)
2. Mavzu bo'yicha pozitsiyani aniqlash
3. Vaqt o'tishi bilan pozitsiya o'zgarishini kuzatish
4. Konsensusga erishilganda: "🤝 Kelishuvga erishildi!" baneri
5. Qarama-qarshilik kuchaysa: "⚡ Bahsli nuqta aniqlandi!" ogohlantirish
```

### F8 — AI Moderator Rejimi

```
Foydalanuvchi o'rniga maxsus "Moderator" agentni qo'shish imkoni.

Moderator vazifalari:
- Suhbat chiqimini kuzatish
- Mavzu chetga chiqqanda: "Iltimos, asosiy mavzuga qaytaylik..."
- Kimdir ko'p gapirsa: "Boshqalar fikrin ham eshitaylik..."
- Xulosa qilish: "Hozirgi asosiy fikrlar: ..."
- Yangi savol berish: suhbat to'xtab qolsa

System prompt example for Moderator:
  "Sen intellektual muhokamani boshqaruvchi moderatorsing.
   Suhbat maqsadga yo'nalgan va barcha ishtirokchilar tengdek
   ishtiroki bo'lishi uchun nazorat qilasan.
   Qisqa va aniq gapirasan. Hech qachon o'z fikringni bildirmassan."
```

### F9 — Tema va Mavzu Inyeksiyasi

```
UI elementlari:
┌─────────────────────────────────────────┐
│ 💉 Mavzu qo'shish:                       │
│ [🌍 Texnologiya] [🏛 Falsafa] [⚖ Huquq] │
│ [🧬 Fan] [🎨 San'at] [💰 Iqtisod] [+]   │
│                                          │
│ Yoki o'zingiz yozing:                    │
│ [________________________] [Kirgiz]     │
└─────────────────────────────────────────┘

Inyeksiya mexanizmi:
- System xabar sifatida: "[MODERATOR]: Yangi mavzu: [mavzu]"
- Barcha agentlar ushbu xabarni ko'radi va yangi mavzuga ko'chadi
- Mavzu badge yangilanadi
- Chat tarixida marker (---Mavzu o'zgardi---) ko'rinadi
```

### F10 — Eksport Va Arxivlash

```
Eksport formatlari:
├── JSON  → To'liq metadata, token ma'lumotlari, timestamps bilan
├── TXT   → Oddiy matn formati (ism: xabar)
├── MD    → Markdown formati, agent nomi heading sifatida
├── PDF   → Chiroyli dizayn bilan (jsPDF orqali)
└── HTML  → Standalone HTML fayl (offline ko'rish uchun)

Arxivlash:
- Har 24 soat avtomatik arxivlash
- IndexedDB da local saqlash (100 MB limit)
- Export → Google Drive / Dropbox integratsiya (keyingi versiya)
```

### F11 — Yashirin Kuzatuvchi Rejimi (Ghost Mode)

```
Foydalanuvchi interfeysi:
- "👻 Ghost Mode" tugmasi
- Faol bo'lganda: foydalanuvchining xabarlari AI larga KO'RINMAYDI
- Faqat kuzatish rejimi
- Real-time izohlar yozish (faqat o'ziga ko'rinadigan sharhlar)
- Suhbat tugagach, sharhlarni export qilish

Foydalanish holatlari:
- Tadqiqot: AI lar o'z holiga qanday gaplashishini kuzatish
- Test: Muayyan holatda AI lar qanday xulosa chiqarishini tekshirish
- Ta'lim: Talabalar AI lar suhbatini kuzatishi
```

### F12 — Ko'p Til Qo'llab-Quvvatlashi

```
Har bir agent alohida tilda gapira oladi:

agent_language_settings:
  language: "uz" | "en" | "de" | "ru" | "ar" | "auto"
  
"auto" rejimida:
  - Oldingi xabar tilini aniqlaydi
  - O'sha tilda javob beradi
  - Aralash suhbatda: ko'p tillik o'qish tajribasi

UI:
  - Har bir agent kartasida bayroq emoji (🇺🇿 🇺🇸 🇩🇪)
  - Global til o'zgartirish tugmasi
  - Real-time tarjima (ixtiyoriy, alohida API bilan)
```

### F13 — Suhbat Replaying va Tezlashtirish

```
Tarix ko'rish paneli:
- Suhbatni boshidan "replay" qilish imkoni
- Tezlik: 0.5x, 1x, 2x, 5x, ∞ (instant show)
- Muayyan xabarga "warp" qilish (vaqt sayohati)
- Suhbatning "muhim lahzalari" avtomatik belgilash
  (konsensus, ziddiyat, g'ayrioddiy fikr kiritilgan paytlar)
```

---

## 8. UI/UX DIZAYN TALABLARI

### 8.1 Rang Sxemasi

```css
:root {
  /* Asosiy ranglar */
  --bg-primary: #0A0A0F;         /* Qorong'u fon */
  --bg-secondary: #111118;       /* Karta fonlari */
  --bg-tertiary: #1A1A24;        /* Input fonlari */
  --border: rgba(255,255,255,0.08);
  --border-active: rgba(255,255,255,0.2);
  
  /* Matn */
  --text-primary: #F0F0F5;
  --text-secondary: #888899;
  --text-muted: #444455;
  
  /* Aksent ranglar */
  --accent-purple: #7C3AED;
  --accent-blue: #3B82F6;
  --accent-green: #10B981;
  --accent-amber: #F59E0B;
  --accent-red: #EF4444;
  
  /* Agent ranglari (avtomatik beriladi) */
  --agent-colors: [
    #7C3AED, #3B82F6, #10B981, #F59E0B,
    #EF4444, #EC4899, #06B6D4, #84CC16,
    #F97316, #A855F7, #14B8A6, #EAB308
  ];
}
```

### 8.2 Animatsiya Kutubxonasi

```javascript
animations = {
  // Agent javob yozayotganda
  thinking: "pulse + typing dots (3 nuqta ketma-ket paydo bo'ladi)",
  
  // Yangi xabar kelganda
  messageAppear: "slide-up + fade-in (200ms ease-out)",
  
  // Agent skip qilganda
  agentSkip: "card opacity → 0.4 (300ms), keyin qaytish (500ms)",
  
  // Yangi agent qo'shilganda
  agentJoin: "scale 0 → 1 + card shimmer effekti (400ms)",
  
  // Xabar stream kelganda (token by token)
  streamCursor: "yangi harf paydo bo'lganda cursor blinks",
  
  // Konsensus topilganda
  consensus: "confetti burst + banner slide-down"
}
```

### 8.3 Responsive Dizayn

```
Desktop (>1200px): 3 panel (sidebar + chat + right panel)
Tablet (768-1200px): 2 panel (sidebar yig'iladi)
Mobile (<768px): 1 panel, bottom navigation

Agent kartalar:
Desktop: horizontal scroll (barcha agentlar bir qatorda)
Mobile: vertical stack, kichikroq kartalar
```

---

## 9. XAVFSIZLIK VA ISHLASH

### 9.1 API Key Xavfsizligi

```
BACKEND tomonida:
- API keylar faqat serverda saqlanadi (frontend ko'rmaydi)
- DB da AES-256 shifrlash bilan saqlash
- Environment variables (.env) orqali yuklash
- Key rotation imkoni (provider settings da)

FRONTEND tomonida:
- API keylar hech qachon frontendga uzatilmaydi
- Faqat backend orqali so'rovlar yuboriladi
- localStorage da HECH QACHON API key saqlanmaydi

Demo rejimi (development):
- Mock adapters — haqiqiy API chaqirmasdan test qilish
- Seed data bilan boshlash
```

### 9.2 Rate Limiting

```python
rate_limits = {
    "groq": {
        "requests_per_minute": 30,
        "tokens_per_minute": 14400,
        "strategy": "exponential_backoff"
    },
    "gemini": {
        "requests_per_minute": 60,
        "tokens_per_minute": 32000,
        "strategy": "queue_and_delay"
    }
}

# Avtonom agent tezligini rate limit ga moslash
auto_speed_adjust = True  # Agar limit yaqinlashsa, speed_ms oshirish
```

### 9.3 Ishlash Optimizatsiyasi

```
Frontend:
- Virtual scrolling (10,000+ xabar bo'lsa ham silliq)
- Message deduplication (WebSocket retry da takrorlanmaslik)
- Lazy loading (eski xabarlarni pastga scroll qilganda yuklash)
- Worker thread (markdown parsing asosiy threadni bloklamasin)

Backend:
- Async/await barcha joyda
- Connection pooling (DB uchun)
- Message queue (agent navbatini boshqarish)
- Caching (provider modellari ro'yxati, agent configs)
```

---

## 10. SOZLASH FAYLLAR TUZILMASI

```
project/
├── backend/
│   ├── main.py                 # FastAPI app + WebSocket
│   ├── config.py               # Sozlamalar
│   ├── database.py             # DB ulanish
│   ├── models/
│   │   ├── provider.py
│   │   ├── agent.py
│   │   ├── conversation.py
│   │   └── message.py
│   ├── adapters/
│   │   ├── base.py             # BaseAIAdapter
│   │   ├── groq_adapter.py
│   │   ├── gemini_adapter.py
│   │   ├── openai_adapter.py
│   │   ├── anthropic_adapter.py
│   │   └── custom_adapter.py
│   ├── services/
│   │   ├── turn_manager.py
│   │   ├── memory_manager.py
│   │   ├── ai_router.py
│   │   └── conversation_service.py
│   ├── routers/
│   │   ├── providers.py
│   │   ├── agents.py
│   │   ├── conversations.py
│   │   └── analytics.py
│   └── requirements.txt
│
├── frontend/
│   ├── index.html
│   ├── style.css
│   ├── app.js                  # Asosiy app logic
│   ├── components/
│   │   ├── AgentCard.js
│   │   ├── MessageBubble.js
│   │   ├── ChatStream.js
│   │   ├── UserInput.js
│   │   ├── ProviderManager.js
│   │   ├── Analytics.js
│   │   └── SettingsPanel.js
│   ├── services/
│   │   ├── websocket.js        # WS connection
│   │   ├── storage.js          # IndexedDB
│   │   └── api.js              # REST API calls
│   └── utils/
│       ├── markdown.js
│       ├── mentions.js
│       └── theme.js
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 11. QUICK START — BOSHLASH BUYRUQLARI

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env
# .env faylida API keylarni to'ldirish
uvicorn main:app --reload --port 8000

# Frontend (oddiy)
cd frontend
python -m http.server 3000
# yoki
npx serve . -p 3000

# Docker bilan (to'liq)
docker-compose up --build
# → http://localhost:3000 da ochiq
```

---

## 12. MVP VS TO'LIQ VERSIYA

### MVP (Birinchi hafta)
```
✅ 1 ta Groq + 1 ta Gemini agent
✅ Oddiy round-robin navbat
✅ WebSocket orqali real-time
✅ Bazaviy chat UI
✅ Start/Pause/Stop
✅ SQLite DB
```

### V1.0 (Bir oy)
```
✅ Ko'p agent qo'shish (cheksiz)
✅ Ko'p provider
✅ Analytics
✅ Eksport
✅ Foydalanuvchi ishtiroki
✅ @mention tizimi
✅ Provider manager UI
```

### V2.0 (Uch oy)
```
✅ Personality engine
✅ Consensus map
✅ AI Moderator
✅ Replay tizimi
✅ Ko'p til
✅ Mobile responsive
✅ Ghost mode
✅ Tema inject qilish
```

---

*Muallif: Mansurxon (TDYU) — AI Systems Design, 2026*

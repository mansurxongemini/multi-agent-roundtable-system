/* ============================================================================
   AI Society Simulation — frontend controller (Vanilla JS, zero deps).

   Responsibilities
   ----------------
   - REST: manage providers, agents, groups, and memberships.
   - WebSocket: connect to a room, stream the live conversation, and issue the
     God-Mode commands (start/pause/stop, mute, priority floor, human inject,
     topic change).
   - Render the minimalist black UI without any framework.
   ========================================================================== */

const API = "/api";

/* ── Tiny REST helper ─────────────────────────────────────────────────── */
async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || JSON.stringify(data));
  return data;
}

/* ── App state ────────────────────────────────────────────────────────── */
const state = {
  groups: [],
  activeGroup: null,   // full group object (with memberships)
  ws: null,
  thinkingAgent: null,
};

/* ── DOM refs ─────────────────────────────────────────────────────────── */
const $ = (id) => document.getElementById(id);
const el = {
  groupList: $("groupList"),
  roomName: $("roomName"),
  roomTopic: $("roomTopic"),
  statusPill: $("statusPill"),
  startBtn: $("startBtn"),
  pauseBtn: $("pauseBtn"),
  stopBtn: $("stopBtn"),
  agentRow: $("agentRow"),
  chat: $("chat"),
  humanInput: $("humanInput"),
  sendBtn: $("sendBtn"),
  modalBackdrop: $("modalBackdrop"),
  modal: $("modal"),
};

/* ── Utilities ────────────────────────────────────────────────────────── */
const esc = (s) =>
  (s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtTime = (iso) =>
  new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/* ════════════════════════════════════════════════════════════════════════
   GROUPS (rooms)
   ════════════════════════════════════════════════════════════════════════ */
async function loadGroups() {
  const data = await api("/groups/");
  state.groups = data.results || data;
  renderGroupList();
}

function renderGroupList() {
  el.groupList.innerHTML = "";
  state.groups.forEach((g) => {
    const li = document.createElement("li");
    if (state.activeGroup && g.id === state.activeGroup.id) li.classList.add("active");
    li.innerHTML = `<span>${esc(g.name)}</span><span class="mini">${g.member_count}</span>`;
    li.onclick = () => openGroup(g.id);
    el.groupList.appendChild(li);
  });
}

async function openGroup(groupId) {
  const group = await api(`/groups/${groupId}/`);
  state.activeGroup = group;
  renderGroupList();
  el.roomName.textContent = group.name;
  el.roomTopic.textContent = group.topic || "no topic set";
  el.chat.innerHTML = "";
  renderAgentRow();
  enableControls(true);
  connectWS(groupId);
}

function enableControls(on) {
  [el.startBtn, el.pauseBtn, el.stopBtn, el.humanInput, el.sendBtn].forEach(
    (b) => (b.disabled = !on)
  );
}

/* ════════════════════════════════════════════════════════════════════════
   AGENT ROSTER + GOD-MODE PER-AGENT CONTROLS
   ════════════════════════════════════════════════════════════════════════ */
function renderAgentRow() {
  el.agentRow.innerHTML = "";
  const g = state.activeGroup;
  if (!g) return;

  g.memberships.forEach((m) => {
    const card = document.createElement("div");
    card.className = "agent-card";
    card.dataset.agent = m.agent;
    if (m.is_muted) card.classList.add("muted");
    if (m.priority_floor) card.classList.add("floor");

    card.innerHTML = `
      <div class="agent-id">
        <div class="avatar" style="background:${esc(m.agent_color)}22;color:${esc(m.agent_color)}">${esc(m.agent_emoji)}</div>
        <div class="agent-meta">
          <div class="agent-name">${esc(m.agent_name)}</div>
          <div class="agent-model">${esc(m.model_id)}</div>
        </div>
      </div>
      <div class="thinking-slot"></div>
      <div class="agent-actions">
        <button class="chip mute ${m.is_muted ? "on" : ""}">${m.is_muted ? "Unmute" : "Mute"}</button>
        <button class="chip floor ${m.priority_floor ? "on" : ""}">Floor</button>
      </div>`;

    card.querySelector(".mute").onclick = () =>
      send({ action: "mute", agent_id: m.agent, muted: !m.is_muted });
    card.querySelector(".floor").onclick = () =>
      send({ action: "priority_floor", agent_id: m.agent, on: !m.priority_floor });

    el.agentRow.appendChild(card);
  });

  // "+ assign agent" tile.
  const add = document.createElement("div");
  add.className = "agent-card";
  add.style.cssText = "align-items:center;justify-content:center;cursor:pointer;color:var(--muted)";
  add.innerHTML = `<div style="font-size:22px">+</div><div style="font-size:11px">Assign agent</div>`;
  add.onclick = openAssignAgentModal;
  el.agentRow.appendChild(add);
}

function setThinking(agentId) {
  document.querySelectorAll(".agent-card").forEach((c) => {
    const slot = c.querySelector(".thinking-slot");
    const isIt = c.dataset.agent === agentId;
    c.classList.toggle("thinking", isIt);
    if (slot) slot.innerHTML = isIt ? `<span class="thinking-dots"><i></i><i></i><i></i></span>` : "";
  });
}
function clearThinking() {
  document.querySelectorAll(".agent-card").forEach((c) => {
    c.classList.remove("thinking");
    const slot = c.querySelector(".thinking-slot");
    if (slot) slot.innerHTML = "";
  });
}

/* ════════════════════════════════════════════════════════════════════════
   WEBSOCKET — realtime stream + control channel
   ════════════════════════════════════════════════════════════════════════ */
function connectWS(groupId) {
  if (state.ws) { state.ws.onclose = null; state.ws.close(); }
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${scheme}://${location.host}/ws/groups/${groupId}/`);
  state.ws = ws;

  ws.onmessage = (e) => handleEvent(JSON.parse(e.data));
  ws.onclose = () => toast("disconnected");
}

function send(payload) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(payload));
  }
}

function handleEvent({ event, data }) {
  switch (event) {
    case "status":     applyStatus(data); break;
    case "history":    data.messages.forEach(addMessage); scrollChat(); break;
    case "message":    clearThinking(); addMessage(data); scrollChat(); break;
    case "thinking":   setThinking(data.agent_id); state.thinkingAgent = data.agent_id; break;
    case "skipped":    clearThinking(); if (data.reason === "skip") toast(`${agentName(data.agent_id)} skipped`); break;
    case "topic_changed": el.roomTopic.textContent = data.topic; break;
    case "agent_flag": applyAgentFlag(data); break;
    case "summarizing": toast(`compressing memory (~${data.tokens} tokens)…`); break;
    case "info":       toast(data.message); break;
    case "error":      toast(`error: ${data.message}`); break;
  }
}

function applyStatus(data) {
  if (data.status) {
    el.statusPill.textContent = data.status;
    el.statusPill.className = `status-pill ${data.status}`;
  }
  if (data.topic !== undefined && data.topic) el.roomTopic.textContent = data.topic;
}

function applyAgentFlag(data) {
  const g = state.activeGroup;
  if (!g) return;
  const m = g.memberships.find((x) => x.agent === data.agent_id);
  if (!m) return;
  if ("is_muted" in data) m.is_muted = data.is_muted;
  if ("priority_floor" in data) m.priority_floor = data.priority_floor;
  renderAgentRow();
}

function agentName(agentId) {
  const m = state.activeGroup?.memberships.find((x) => x.agent === agentId);
  return m ? m.agent_name : "agent";
}

/* ── Chat rendering ───────────────────────────────────────────────────── */
function addMessage(m) {
  if (m.role === "human" || m.role === "system") {
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    const label = m.role === "human" ? "ADMIN / GOD" : "SYSTEM";
    div.innerHTML = `
      <div class="msg-head"><span class="msg-name">${label}</span>
        <span class="msg-time">${fmtTime(m.created_at)}</span></div>
      <div class="msg-body">${esc(m.content)}</div>`;
    el.chat.appendChild(div);
    return;
  }
  const div = document.createElement("div");
  div.className = "msg agent";
  div.innerHTML = `
    <div class="msg-head">
      <span class="msg-avatar" style="background:${esc(m.agent_color)}22;color:${esc(m.agent_color)}">${esc(m.agent_emoji)}</span>
      <span class="msg-name" style="color:${esc(m.agent_color)}">${esc(m.agent_name)}</span>
      <span class="msg-time">${fmtTime(m.created_at)}</span>
      <span class="msg-tok">${m.tokens_used} tok · ${m.response_ms}ms</span>
    </div>
    <div class="msg-body">${esc(m.content)}</div>`;
  el.chat.appendChild(div);
}

function toast(text) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = `— ${text} —`;
  el.chat.appendChild(t);
  scrollChat();
}
function scrollChat() { el.chat.scrollTop = el.chat.scrollHeight; }

/* ════════════════════════════════════════════════════════════════════════
   TOP-BAR CONTROLS + HUMAN INTERVENTION
   ════════════════════════════════════════════════════════════════════════ */
el.startBtn.onclick = () => send({ action: "start" });
el.pauseBtn.onclick = () => send({ action: "pause" });
el.stopBtn.onclick = () => send({ action: "stop" });

function sendHuman() {
  const text = el.humanInput.value.trim();
  if (!text) return;
  send({ action: "human_message", content: text });
  el.humanInput.value = "";
}
el.sendBtn.onclick = sendHuman;
el.humanInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendHuman();
});

/* ════════════════════════════════════════════════════════════════════════
   MODALS — generic open/close
   ════════════════════════════════════════════════════════════════════════ */
function openModal(html) {
  el.modal.innerHTML = html;
  el.modalBackdrop.hidden = false;
}
function closeModal() { el.modalBackdrop.hidden = true; el.modal.innerHTML = ""; }
el.modalBackdrop.addEventListener("click", (e) => {
  if (e.target === el.modalBackdrop) closeModal();
});

/* ── New room modal ───────────────────────────────────────────────────── */
$("newGroupBtn").onclick = () => {
  openModal(`
    <h2>New room</h2>
    <div class="field"><label>Name</label><input id="g_name" placeholder="Tech Innovators" /></div>
    <div class="field"><label>Topic</label><input id="g_topic" placeholder="The future of AGI governance" /></div>
    <div class="row">
      <div class="field"><label>Turn mode</label>
        <select id="g_mode">
          <option value="sequential">Sequential</option>
          <option value="random">Random</option>
          <option value="weighted">Weighted</option>
        </select></div>
      <div class="field"><label>Speed (ms)</label><input id="g_speed" type="number" value="3000" /></div>
    </div>
    <div class="modal-actions">
      <button class="chip" onclick="closeModal()">Cancel</button>
      <button class="ctrl" id="g_save">Create</button>
    </div>`);
  $("g_save").onclick = async () => {
    await api("/groups/", { method: "POST", body: {
      name: $("g_name").value.trim() || "Untitled room",
      topic: $("g_topic").value.trim(),
      turn_mode: $("g_mode").value,
      speed_ms: parseInt($("g_speed").value) || 3000,
    }});
    closeModal();
    await loadGroups();
  };
};

/* ── Providers modal ──────────────────────────────────────────────────── */
$("manageProvidersBtn").onclick = async () => {
  const adapters = (await api("/meta/adapters/")).adapter_types;
  const providers = await api("/providers/");
  const list = (providers.results || providers).map((p) => `
    <div class="list-row">
      <div><strong>${esc(p.name)}</strong> <span class="meta">${esc(p.adapter_type)}</span></div>
      <span class="tag ${p.has_key ? "" : "off"}">${p.has_key ? "key set" : "no key"}</span>
    </div>`).join("");

  openModal(`
    <h2>Providers &amp; API keys</h2>
    ${list || '<p class="hint">No providers yet.</p>'}
    <h3>Add provider</h3>
    <div class="row">
      <div class="field"><label>Name</label><input id="p_name" placeholder="Groq" /></div>
      <div class="field"><label>Type</label>
        <select id="p_type">${adapters.map((a) => `<option>${a}</option>`).join("")}</select></div>
    </div>
    <div class="field"><label>Base URL (optional)</label><input id="p_url" placeholder="defaults per adapter" /></div>
    <div class="field"><label>API key</label><input id="p_key" type="password" placeholder="stored encrypted, never returned" /></div>
    <div class="modal-actions">
      <button class="chip" onclick="closeModal()">Close</button>
      <button class="ctrl" id="p_save">Save provider</button>
    </div>`);
  $("p_save").onclick = async () => {
    await api("/providers/", { method: "POST", body: {
      name: $("p_name").value.trim(),
      adapter_type: $("p_type").value,
      base_url: $("p_url").value.trim(),
      api_key: $("p_key").value,
    }});
    closeModal();
  };
};

/* ── Agents modal ─────────────────────────────────────────────────────── */
$("manageAgentsBtn").onclick = async () => {
  const provData = await api("/providers/");
  const provList = provData.results || provData;
  const agents = await api("/agents/");
  const list = (agents.results || agents).map((a) => `
    <div class="list-row">
      <div>${esc(a.avatar_emoji)} <strong>${esc(a.name)}</strong>
        <span class="meta">${esc(a.model_id)} · ${esc(a.provider_name)}</span></div>
    </div>`).join("");

  openModal(`
    <h2>Agents</h2>
    ${list || '<p class="hint">No agents yet.</p>'}
    <h3>New agent</h3>
    <div class="row">
      <div class="field"><label>Name</label><input id="a_name" placeholder="Skeptic" /></div>
      <div class="field"><label>Emoji</label><input id="a_emoji" value="🤖" /></div>
      <div class="field"><label>Color</label><input id="a_color" type="color" value="#7C3AED" /></div>
    </div>
    <div class="row">
      <div class="field"><label>Provider</label>
        <select id="a_provider">${provList.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select></div>
      <div class="field"><label>Model ID</label><input id="a_model" placeholder="llama3-70b-8192" /></div>
    </div>
    <div class="field"><label>System prompt (persona)</label>
      <textarea id="a_prompt" placeholder="You are an aggressive skeptic..."></textarea></div>
    <div class="row">
      <div class="field"><label>Temperature</label><input id="a_temp" type="number" step="0.1" value="0.8" /></div>
      <div class="field"><label>Max tokens</label><input id="a_max" type="number" value="320" /></div>
    </div>
    <div class="modal-actions">
      <button class="chip" onclick="closeModal()">Close</button>
      <button class="ctrl" id="a_save">Create agent</button>
    </div>`);
  $("a_save").onclick = async () => {
    await api("/agents/", { method: "POST", body: {
      name: $("a_name").value.trim(),
      avatar_emoji: $("a_emoji").value || "🤖",
      avatar_color: $("a_color").value,
      provider: $("a_provider").value,
      model_id: $("a_model").value.trim(),
      system_prompt: $("a_prompt").value.trim(),
      temperature: parseFloat($("a_temp").value) || 0.7,
      max_tokens: parseInt($("a_max").value) || 320,
    }});
    closeModal();
  };
};

/* ── Assign agent to current room ─────────────────────────────────────── */
async function openAssignAgentModal() {
  if (!state.activeGroup) return;
  const agents = await api("/agents/");
  const assigned = new Set(state.activeGroup.memberships.map((m) => m.agent));
  const options = (agents.results || agents)
    .filter((a) => !assigned.has(a.id))
    .map((a) => `<option value="${a.id}">${esc(a.avatar_emoji)} ${esc(a.name)} · ${esc(a.model_id)}</option>`)
    .join("");

  openModal(`
    <h2>Assign agent to “${esc(state.activeGroup.name)}”</h2>
    ${options
      ? `<div class="field"><label>Agent</label><select id="m_agent">${options}</select></div>
         <div class="modal-actions">
           <button class="chip" onclick="closeModal()">Cancel</button>
           <button class="ctrl" id="m_save">Assign</button>
         </div>`
      : '<p class="hint">All agents are already assigned. Create more in the Agents panel.</p>'}`);

  if (options) {
    $("m_save").onclick = async () => {
      await api(`/groups/${state.activeGroup.id}/members/`, {
        method: "POST", body: { agent: $("m_agent").value },
      });
      closeModal();
      await openGroup(state.activeGroup.id); // refresh memberships
    };
  }
}

// Expose closeModal for inline onclick handlers.
window.closeModal = closeModal;

/* ── Boot ─────────────────────────────────────────────────────────────── */
loadGroups().catch((e) => console.error(e));

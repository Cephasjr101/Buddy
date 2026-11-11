/* AgentHub MVP SPA */
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const state = { user: null, agents: [] };   // session lives in an HttpOnly cookie (invisible to JS)

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function api(path, opts = {}) {
  const r = await fetch(path, { method: opts.method || "GET",
    credentials: "same-origin",   // sends the HttpOnly session cookie
    headers: { "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail ? (Array.isArray(d.detail) ? d.detail[0].msg : d.detail) : r.statusText);
  return d;
}
const sendForm = (path, formData, method = "POST") => fetch(path, { method,
  credentials: "same-origin",
  body: formData }).then(async r => { const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || r.statusText); return d; });

function toast(msg, type = "") { const t = document.createElement("div");
  t.className = "toast " + type; t.textContent = msg; $("#toast-root").appendChild(t);
  setTimeout(() => t.remove(), 4500); }

function chrome() {
  const authed = !!state.user;
  $$("#mainnav [data-auth]").forEach(a => a.hidden = !authed);
  $("#auth-btn").textContent = authed ? (state.user?.name || "Account") + " \u25be" : "Sign in";
  $("#auth-btn").onclick = () => authed ? location.hash = "#/account" : location.hash = "#/login";
  $("#auth-btn").oncontextmenu = e => { if (authed) { e.preventDefault(); location.hash = "#/logout"; } return false; };
}

/* ---------------- views ---------------- */
function viewHome() {
  $("#app").innerHTML = `
  <div class="hero"><h1>Meet your AI agents</h1>
    <p>Name them. Give them a voice. Send a voice note - they book appointments,
    make calls, play music, send emails, remind you, and market your business 3-5 times a day.</p>
    <p style="margin-top:1rem"><a class="btn" href="#/agents">${state.user ? "My agents" : "Get started"}</a></p></div>
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">
    <div class="card"><span class="badge">Voice notes in</span><h3>Speak, don't type</h3>
      <p class="small muted">Record a note - transcription runs locally with VoiceStudio.</p></div>
    <div class="card"><span class="badge">Calls out</span><h3>Agents that phone</h3>
      <p class="small muted">"Call Kofi at 3pm" - your agent dials via Twilio.</p></div>
    <div class="card"><span class="badge">Marketing</span><h3>Daily auto-posts</h3>
      <p class="small muted">Business agents write and publish posts 3-5 times daily.</p></div>
  </div>`;
}

function viewLogin() {
  $("#app").innerHTML = `<div class="form-card"><h2>Sign in</h2>
    <div class="field"><label>Email</label><input id="li-email" type="email"></div>
    <div class="field"><label>Password</label><input id="li-pass" type="password"></div>
    <button class="btn" id="li-btn" style="width:100%">Sign in</button>
    <p class="small" style="margin-top:.9rem">New? <a href="#/register">Create an account</a>
     &middot; <a href="#/forgot">Forgot password?</a></p></div>`;
  $("#li-btn").onclick = async () => { try {
    const d = await api("/api/auth/login", { method: "POST", body: { email: $("#li-email").value, password: $("#li-pass").value } });
    state.user = { name: d.name }; chrome(); toast("Welcome back", "success"); location.hash = "#/agents";
  } catch (e) { toast(e.message, "error"); } };
}

function viewForgot() {
  $("#app").innerHTML = `<div class="form-card"><h2>Forgot password</h2>
    <div class="field"><label>Email</label><input id="fg-email" type="email"></div>
    <button class="btn" id="fg-btn" style="width:100%">Send reset link</button>
    <p class="small" style="margin-top:.9rem"><a href="#/login">&larr; Back to sign in</a></p>
    <div id="fg-out" class="small" style="margin-top:.8rem"></div></div>`;
  $("#fg-btn").onclick = async () => { try {
    const d = await api("/api/auth/forgot-password", { method: "POST", body: { email: $("#fg-email").value } });
    let html = `<p>${esc(d.message)}</p>`;
    if (d.dev_link) html += `<p>Dev mode (no SMTP yet):<br><a href="${esc(d.dev_link)}" style="color:var(--teal)">${esc(d.dev_link.slice(0, 70))}...</a></p>`;
    $("#fg-out").innerHTML = html;
  } catch (e) { toast(e.message, "error"); } };
}

function viewReset(token) {
  $("#app").innerHTML = `<div class="form-card"><h2>Set a new password</h2>
    <p class="small muted">The reset link expires 15 minutes after it was created.</p>
    <div class="field"><label>New password (min 6)</label><input id="rs-pass" type="password"></div>
    <button class="btn" id="rs-btn" style="width:100%">Update password</button></div>`;
  $("#rs-btn").onclick = async () => { try {
    const d = await api("/api/auth/reset-password", { method: "POST", body: { token, new_password: $("#rs-pass").value } });
    toast(d.message, "success"); location.hash = "#/login";
  } catch (e) { toast(e.message, "error"); } };
}
function viewRegister() {
  $("#app").innerHTML = `<div class="form-card"><h2>Create account</h2>
    <div class="field"><label>Full name *</label><input id="rg-name"></div>
    <div class="field"><label>Email *</label><input id="rg-email" type="email"></div>
    <div class="field"><label>Phone</label><input id="rg-phone"></div>
    <div class="field"><label>Password (min 6) *</label><input id="rg-pass" type="password"></div>
    <label class="small" style="display:flex;gap:.5rem;align-items:flex-start;margin-bottom:.5rem">
      <input type="checkbox" id="rg-age" style="margin-top:.2rem"> <span>I confirm I am 16 years or older *</span></label>
    <label class="small" style="display:flex;gap:.5rem;align-items:flex-start;margin-bottom:.8rem">
      <input type="checkbox" id="rg-terms" style="margin-top:.2rem"> <span>I agree to the <a href="#/terms" style="color:var(--teal)">Terms</a> and <a href="#/privacy" style="color:var(--teal)">Privacy Policy</a> *</span></label>
    <button class="btn" id="rg-btn" style="width:100%">Create account</button>
    <p class="small" style="margin-top:.9rem">Have an account? <a href="#/login">Sign in</a></p></div>`;
  $("#rg-btn").onclick = async () => { try {
    const d = await api("/api/auth/register", { method: "POST", body: {
      name: $("#rg-name").value, email: $("#rg-email").value, phone: $("#rg-phone").value, password: $("#rg-pass").value,
      age_consent: $("#rg-age").checked, terms_consent: $("#rg-terms").checked } });
    state.user = { name: d.name };
    chrome(); toast("Account created", "success"); location.hash = "#/agents";
  } catch (e) { toast(e.message, "error"); } };
}
function viewAccount() {
  if (!state.user) { location.hash = "#/login"; return; }
  $("#app").innerHTML = `<h2>Account</h2>
  <div class="grid" style="grid-template-columns:1fr 1fr;align-items:start">
    <div class="panel"><h3>Change password</h3>
      <div class="field"><label>Current password</label><input id="cp-cur" type="password"></div>
      <div class="field"><label>New password</label><input id="cp-new" type="password"></div>
      <button class="btn btn-sm" id="cp-btn">Update password</button></div>
    <div class="panel" style="border-color:#7f1d1d"><h3 style="color:var(--red)">Delete account</h3>
      <p class="small muted">Deletes your account, agents, messages, tasks and posts permanently.</p>
      <div class="field"><label>Confirm with password</label><input id="del-pass" type="password"></div>
      <button class="btn btn-danger btn-sm" id="del-btn">Delete everything</button>
      <p style="margin-top:.8rem"><a href="/api/export" style="color:var(--teal)" class="small">Download all my data (JSON)</a></p></div>
  </div>`;
  $("#cp-btn").onclick = async () => { try {
    const d = await api("/api/auth/change-password", { method: "POST",
      body: { current_password: $("#cp-cur").value, new_password: $("#cp-new").value } });
    toast(d.message || "Updated", "success");
  } catch (e) { toast(e.message, "error"); } };
  $("#del-btn").onclick = async () => { if (!confirm("Permanently delete your account and all data?")) return;
    try { const d = await api("/api/auth/delete-account", { method: "POST", body: { password: $("#del-pass").value } });
      state.user = null; chrome(); toast(d.message || "Deleted"); location.hash = "#/";
    } catch (e) { toast(e.message, "error"); } };
}

/* ---------------- agents ---------------- */
async function viewAgents() {
  if (!state.user) { location.hash = "#/login"; return; }
  $("#app").innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.6rem">
    <h2>My Agents</h2><button class="btn btn-sm" id="new-agent">+ New agent</button></div>
    <div id="agent-list" class="grid agents-grid"><p class="muted">Loading...</p></div>
    <div id="agent-form" style="display:none"></div>`;
  $("#new-agent").onclick = showAgentForm;
  try {
    const d = await api("/api/agents");
    state.agents = d.agents;
    $("#agent-list").innerHTML = d.agents.length ? d.agents.map(a => `
      <div class="card agent-card"><span class="badge">${a.role}</span>
        <h3>${esc(a.name)}</h3>
        <p class="small muted">${esc(a.business || a.personality || "Your assistant")}</p>
        <p class="small muted">Posts/day: ${a.posts_per_day}</p>
        <p><a class="btn btn-sm" href="#/agent/${a.id}">Open</a></p>
      </div>`).join("") : `<div class="empty" style="grid-column:1/-1">
        <h3>No agents yet</h3><p class="muted">Create one - personal or business - and give it a name.</p></div>`;
  } catch (e) { $("#agent-list").innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
function showAgentForm() {
  $("#agent-form").style.display = "block";
  $("#agent-form").innerHTML = `<div class="form-card" style="margin:0 0 1rem">
    <h3>New agent</h3>
    <div class="field"><label>Name * (e.g. Ama, Zuri, RoboSales)</label><input id="ag-name" placeholder="Ama"></div>
    <div class="form-row"><div class="field"><label>Type</label>
      <select id="ag-role"><option value="personal">Personal</option><option value="business">Business (auto-markets)</option></select></div>
    <div class="field"><label>Posts per day</label><select id="ag-posts">
      <option>3</option><option>4</option><option>5</option></select></div></div>
    <div class="field"><label>Business name (business agents)</label><input id="ag-biz" placeholder="RockBuy Store"></div>
    <div class="field"><label>Personality</label><input id="ag-pers" placeholder="Warm, professional, brief"></div>
    <p style="display:flex;gap:.5rem"><button class="btn btn-sm" id="ag-save">Create</button>
    <button class="btn btn-ghost btn-sm" id="ag-cancel">Cancel</button></p></div>`;
  $("#ag-cancel").onclick = () => $("#agent-form").style.display = "none";
  $("#ag-save").onclick = async () => { try {
    await api("/api/agents", { method: "POST", body: {
      name: $("#ag-name").value, role: $("#ag-role").value,
      posts_per_day: +$("#ag-posts").value, business: $("#ag-biz").value,
      personality: $("#ag-pers").value } });
    toast("Agent created", "success"); viewAgents();
  } catch (e) { toast(e.message, "error"); } };
}

async function viewAgent(id) {
  const d = await api("/api/agents");
  const a = d.agents.find(x => x.id === +id);
  if (!a) { location.hash = "#/agents"; return; }
  $("#app").innerHTML = `
    <p><a href="#/agents" class="small">&larr; All agents</a></p>
    <div class="panel" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.6rem">
      <div><span class="badge">${a.role}</span><h2 style="margin:.1rem 0">${esc(a.name)}</h2>
      <p class="small muted" style="margin:0">${esc(a.business || a.personality || "")}</p></div>
      <div style="display:flex;gap:.5rem;flex-wrap:wrap">
        <label class="btn btn-outline btn-sm" style="cursor:pointer">Clone voice
          <input id="vc-file" type="file" accept="audio/*" hidden></label>
        <button class="btn btn-danger btn-sm" id="ag-del">Delete</button>
      </div></div>
    <div class="panel" style="padding:0">
      <div class="chat-box" id="chat-box"><p class="muted small" style="align-self:center">
        Send a message or hold the mic. Try: "remind me to call mum at 6pm" or "create a marketing post"</p></div>
      <div class="voice-row">
        <input id="chat-text" placeholder="Type or use the mic...">
        <button class="mic" id="mic-btn" title="Hold to record (click to start/stop)">&#127908;</button>
        <button class="btn btn-sm" id="send-btn">Send</button>
      </div></div>`;
  $("#ag-del").onclick = async () => { if (confirm("Delete agent " + a.name + "?")) {
    await api("/api/agents/" + id, { method: "DELETE" }); toast("Deleted"); location.hash = "#/agents"; } };
  $("#vc-file").onchange = async e => { if (!e.target.files[0]) return; toast("Cloning voice...");
    try { const fd = new FormData(); fd.append("sample", e.target.files[0]);
      const r = await sendForm(`/api/agents/${id}/clone-voice`, fd);
      toast("Voice cloned: " + r.voice_id, "success");
    } catch (err) { toast(err.message, "error"); } };
  const sendText = async () => { const t = $("#chat-text").value.trim(); if (!t) return;
    $("#chat-text").value = ""; addMsg("user", t);
    try { const r = await api(`/api/agents/${id}/text`, { method: "POST", body: { text: t } });
      addMsg("agent", r.message || "Done", r.intent, r.link);
    } catch (e) { addMsg("agent", e.message); } };
  $("#send-btn").onclick = sendText;
  $("#chat-text").onkeydown = e => { if (e.key === "Enter") sendText(); };

  let rec = null, chunks = [], recording = false;
  $("#mic-btn").onclick = async () => {
    if (recording) { rec.stop(); return; }
    try { const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      rec = new MediaRecorder(stream); chunks = [];
      rec.ondataavailable = e => chunks.push(e.data);
      rec.onstop = async () => {
        recording = false; $("#mic-btn").classList.remove("rec"); stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
        addMsg("user", "&#127908; Voice note...");
        try { const fd = new FormData(); fd.append("note", blob, "note.webm");
          const r = await sendForm(`/api/agents/${id}/voice`, fd);
          const box = $("#chat-box"); box.lastChild.remove();
          addMsg("user", "&#127908; " + (r.transcript || ""));
          addMsg("agent", r.message || "Done", r.intent, r.link);
          if (r.audio) new Audio(r.audio).play();
        } catch (e) { const box = $("#chat-box"); box.lastChild.remove(); addMsg("agent", e.message); }
      };
      rec.start(); recording = true; $("#mic-btn").classList.add("rec");
      toast("Recording... click mic to stop");
    } catch { toast("Microphone access denied", "error"); }
  };
  loadMessages(id);
}
function addMsg(who, content, intent, link) {
  const box = $("#chat-box");
  const div = document.createElement("div");
  div.className = "msg " + who;
  div.innerHTML = esc(content) + (link ? `<br><a href="${esc(link)}" target="_blank" style="color:var(--teal)">Open &#9654;</a>` : "");
  if (intent && intent.intent && intent.intent !== "none")
    div.innerHTML += `<span class="intent-tag">intent: ${esc(intent.intent)}</span>`;
  box.appendChild(div); box.scrollTop = box.scrollHeight;
}
async function loadMessages(id) {
  try { const d = await api(`/api/agents/${id}/messages`);
    d.messages.forEach(m => addMsg(m.kind === "agent" ? "agent" : "user",
      m.content.startsWith("{") ? (JSON.parse(m.content).message || m.content) : m.content,
      JSON.parse(m.intent || "{}")));
  } catch {}
}

/* ---------------- records / posts / skills ---------------- */
async function viewTasks() {
  if (!state.user) { location.hash = "#/login"; return; }
  const d = await api("/api/tasks");
  $("#app").innerHTML = `<h2>Records</h2><div class="panel"><table>
    <tr><th>Kind</th><th>Details</th><th>Status</th><th>When</th><th>Result</th></tr>` +
    (d.tasks.map(t => `<tr><td>${esc(t.kind)}</td>
      <td class="small">${esc(Object.entries(t.payload).map(([k,v]) => k + ": " + v).join(", ").slice(0, 90))}</td>
      <td><span class="status ${t.status}">${t.status}</span></td>
      <td class="small">${esc(t.run_at || t.created_at || "")}</td>
      <td class="small">${esc((t.result || "").slice(0, 60))}</td></tr>`).join("") || "") +
    `</table></div>`;
}
async function viewPosts() {
  if (!state.user) { location.hash = "#/login"; return; }
  const [d, agents] = [await api("/api/posts"), await api("/api/agents")];
  $("#app").innerHTML = `<h2>Marketing</h2>
    <div class="panel post-card"><h3>New post</h3>
    <div class="field"><label>Agent</label><select id="np-agent">
      ${agents.agents.map(a => `<option value="${a.id}">${esc(a.name)} (${a.role})</option>`).join("")}</select></div>
    <textarea id="np-text" placeholder="Write or let your agent draft it..."></textarea>
    <p style="margin-top:.5rem"><button class="btn btn-sm" id="np-save">Save draft</button></p></div>
    <div id="post-list">${d.posts.map(p => `
      <div class="panel post-card"><p style="white-space:pre-line">${esc(p.content)}</p>
      <p><span class="status ${p.status}">${p.status}</span>
      <span class="small muted">${esc(p.posted_at || "")}</span></p>
      <p><button class="btn btn-sm" data-pub="${p.id}" ${p.status === "posted" ? "disabled" : ""}>Publish now</button></p>
      </div>`).join("") || `<div class="empty">No posts yet - business agents auto-post 3-5 times daily.</div>`}</div>`;
  $("#np-save").onclick = async () => { try {
    await api("/api/posts?aid=" + $("#np-agent").value, { method: "POST", body: { content: $("#np-text").value } });
    toast("Draft saved", "success"); viewPosts();
  } catch (e) { toast(e.message, "error"); } };
  $$("[data-pub]").forEach(b => b.onclick = async () => { try {
    const r = await api("/api/posts/" + b.dataset.pub + "/publish", { method: "POST" });
    toast(r.status === "posted" ? "Posted!" : "Saved - add Facebook/Instagram tokens to auto-publish", r.status === "posted" ? "success" : "");
    viewPosts();
  } catch (e) { toast(e.message, "error"); } });
}
async function viewSkills() {
  if (!state.user) { location.hash = "#/login"; return; }
  const d = await api("/api/skills");
  $("#app").innerHTML = `<h2>Voice & integration skills</h2>
    <p class="muted small">Skills install automatically when their service is configured (env vars / VoiceStudio). Voice cloning, TTS and STT run fully local via <a href="https://github.com/debpalash/VoiceStudio" target="_blank" style="color:var(--teal)">VoiceStudio</a>.</p>
    <div class="panel">${Object.entries(d.skills).map(([k, s]) => `
      <div class="skill-row"><div><strong>${esc(s.label)}</strong>
      <div class="small muted">needs: ${esc(s.needs)}</div></div>
      <span class="status ${s.ready ? "done" : "pending"}">${s.ready ? "READY" : "NOT CONFIGURED"}</span></div>`).join("")}
    </div>`;
}

async function viewLeads() {
  if (!state.user) { location.hash = "#/login"; return; }
  const agents = await api("/api/agents");
  $("#app").innerHTML = `<h2>Leads - find buyers & customers</h2>
  <div class="panel"><div class="form-row">
    <div class="field"><label>What (e.g. phone accessory shops, importers, salons)</label>
      <input id="lf-q" placeholder="phone accessory shops"></div>
    <div class="field"><label>City</label><input id="lf-city" placeholder="Kumasi"></div></div>
    <div class="form-row"><div class="field"><label>Agent</label><select id="lf-agent">
      ${agents.agents.map(a => `<option value="${a.id}">${esc(a.name)}</option>`).join("")}</select></div>
    <div class="field"><label>Source</label><select id="lf-src">
      <option value="places">Google Maps businesses</option><option value="web">Web search</option></select></div></div>
    <button class="btn btn-sm" id="lf-go">Find leads</button>
    <p class="small muted" style="margin:.5rem 0 0">Needs GOOGLE_PLACES_KEY or SERPAPI_KEY in secrets - or say in chat: "find phone shops in Kumasi"</p></div>
    <div id="lead-list"><p class="muted">Loading...</p></div>`;
  async function load() {
    const d = await api("/api/leads");
    $("#lead-list").innerHTML = d.leads.length ? `<div class="panel"><table>
      <tr><th>Name</th><th>Phone</th><th>Address</th><th>Source</th><th>Status</th><th></th></tr>` +
      d.leads.map(l => `<tr><td>${esc(l.name)}</td><td>${esc(l.phone || "-")}</td>
        <td class="small">${esc((l.address || "").slice(0, 50))}</td><td class="small">${esc(l.source)}</td>
        <td><select data-ls="${l.id}">${["new","contacted","qualified","converted","dead"].map(s =>
          `<option ${s === l.status ? "selected" : ""}>${s}</option>`).join("")}</select></td>
        <td style="white-space:nowrap">
          <button class="btn btn-sm" data-wa="${l.id}" data-phone="${esc(l.phone)}">WhatsApp</button>
          <button class="btn btn-outline btn-sm" data-call="${l.id}" data-phone="${esc(l.phone)}">Call</button></td></tr>`).join("") +
      "</table></div>" : `<div class="empty">No leads yet - run a search above.</div>`;
    $$("[data-ls]").forEach(s => s.onchange = async () => { await api("/api/leads/" + s.dataset.ls, { method: "PUT", body: { status: s.value, notes: "" } }); toast("Updated", "success"); });
    $$("[data-wa]").forEach(b => b.onclick = async () => {
      const r = await api(`/api/leads/${b.dataset.wa}/contact`, { method: "POST", body: { channel: "whatsapp" } });
      if (r.link) window.open(r.link, "_blank"); else toast(r.message, "error"); load(); });
    $$("[data-call]").forEach(b => b.onclick = async () => {
      if (!b.dataset.phone) { toast("No phone on this lead", "error"); return; }
      const r = await api(`/api/leads/${b.dataset.call}/contact`, { method: "POST", body: { channel: "call" } });
      toast(r.message, r.ok ? "success" : ""); load(); });
  }
  $("#lf-go").onclick = async () => { const b = $("#lf-go"); b.disabled = true; b.textContent = "Searching...";
    try { const r = await api("/api/leads/find", { method: "POST", body: {
      agent_id: +$("#lf-agent").value, source: $("#lf-src").value,
      query: $("#lf-q").value, city: $("#lf-city").value } });
      toast(r.ok ? `Found ${r.found} - ${r.saved_new} new saved` : r.message, r.ok ? "success" : "error");
      load();
    } catch (e) { toast(e.message, "error"); }
    b.disabled = false; b.textContent = "Find leads"; };
  load();
}

const POLICIES = {
terms: ["Terms & Conditions", `<p><em>Last updated: November 2026. These terms govern use of AgentHub ("the Service").</em></p>
<p><strong>You must be at least 16 years old to use AgentHub.</strong></p>
<h4>1. The Service</h4><p>AgentHub lets you create named software agents ("Agents") that act on instructions you give by text or voice note - including scheduling, reminders, playing music links, drafting and sending emails, placing phone calls, and publishing marketing content to social accounts you connect.</p>
<h4>2. Your instructions, your responsibility</h4><p>Agents act only on your instructions. You are fully responsible for what you instruct, including the content of calls, messages, emails and posts, and for ensuring you have the right to contact the people and numbers you target. You must comply with all laws that apply to you, including marketing-consent and telecommunications laws in your country.</p>
<h4>3. Truthful identification</h4><p>Calls and messages placed by your Agents must honestly identify who is contacting the recipient and on whose behalf. You may not use Agents to impersonate any person or entity.</p>
<h4>4. Accounts & data</h4><p>You may change your password or permanently delete your account - including all Agents, conversations, tasks, posts and voice data - at any time from the account page. Deletion is immediate and irreversible.</p>
<h4>5. Acceptable use</h4><p>The Service may not be used for anything unlawful, harmful, fraudulent, or for unsolicited bulk messaging ("spam"). See our <a href="#/acceptable-use">Acceptable Use Policy</a>.</p>
<h4>6. Third-party services</h4><p>The Service depends on third parties you configure (voice models, telephony, messaging, social platforms). Their terms also apply to your use of them through the Service. We are not responsible for third-party outages or changes.</p>
<h4>7. Service changes & termination</h4><p>We may update the Service or these terms; the version on this page governs new use. We may suspend accounts that breach these terms.</p>
<h4>8. Liability</h4><p>To the maximum extent permitted by law, the Service is provided "as is" and our liability is limited to amounts you paid us in the preceding 12 months. Nothing excludes liability that cannot be excluded by law.</p>
<h4>9. Contact</h4><p>legal@agenthub.example</p>`],
privacy: ["Privacy Policy", `<p><em>Last updated: November 2026.</em></p>
<h4>1. What we store</h4><ul><li>Account: name, email, phone, password (salted hash only).</li>
<li>Your Agents: names, configuration, personalities, business details.</li>
<li>Conversations: text and voice notes you send, and Agent replies.</li>
<li>Records: tasks, appointments, reminders, call and email logs, marketing posts.</li>
<li>Voice models: samples you upload for cloning, and the derived voice models.</li></ul>
<h4>2. Voice data stays yours</h4><p>Transcription (STT), speech (TTS) and voice cloning run on your own infrastructure through the open-source VoiceStudio engine. Voice samples, transcripts and cloned voices never leave your server and are never shared with us or anyone else.</p>
<h4>3. How we use data</h4><p>Solely to operate your Agents: transcribing your notes, executing your commands, keeping your records, and posting to accounts you explicitly connect. We do not sell personal data, and we do not use your voice clones or conversations for any other purpose, including model training.</p>
<h4>4. Sharing</h4><p>We share data only with the services you configure (telephony, messaging, social platforms, email) to execute your instructions, and with authorities where legally required.</p>
<h4>5. Retention & deletion</h4><p>Data is kept while your account exists. Deleting your account permanently removes your profile, Agents, conversations, tasks, posts and voice data immediately. See our <a href="#/ai-policy">AI Voice &amp; Data Policy</a> for voice-specific rights.</p>
<h4>6. Security & your rights</h4><p>Data is encrypted in transit (HTTPS); passwords are hashed. You may request a copy or correction of your data at privacy@agenthub.example.</p>`],
cookies: ["Cookie Policy", `<p><em>Last updated: November 2026.</em></p>
<h4>1. What cookies and storage we use</h4><ul><li><strong>Authentication token</strong> - stored in your browser's localStorage to keep you signed in. Essential; no tracking.</li>
<li><strong>Cart/preferences</strong> - none (AgentHub does not use a cart).</li></ul>
<h4>2. What we do NOT use</h4><p>No advertising cookies, no third-party analytics trackers, no fingerprinting, no cross-site tracking pixels.</p>
<h4>3. Managing storage</h4><p>Signing out removes the auth token. Clearing your browser's site data removes everything. Because the only stored item is your sign-in token, there is nothing to "consent" to beyond using the Service.</p>`],
acceptable: ["Acceptable Use Policy", `<p><em>Last updated: November 2026.</em></p>
<h4>You may not use Agents to:</h4><ul>
<li>Impersonate any person, company, or organization - including military, government, or bank personnel.</li>
<li>Contact anyone who has not consented, or send unsolicited bulk messages or calls (spam).</li>
<li>Harass, threaten, defraud, or deceive any person.</li>
<li>Generate or publish unlawful, hateful, sexually explicit, or misleading content.</li>
<li>Violate platform rules of connected services (telephony, WhatsApp, Meta, etc.).</li>
<li>Interfere with the Service's operation or probe, scan, or breach it.</li>
<li>Process personal data of others without a lawful basis.</li></ul>
<h4>Enforcement</h4><p>Violations may result in immediate suspension or termination of your account, and reporting to relevant authorities or platforms where required. If you become aware of abuse, contact abuse@agenthub.example.</p>`],
ai: ["AI Voice & Data Policy", `<p><em>Last updated: November 2026. How AgentHub handles voice cloning, speech, and agent autonomy.</em></p>
<h4>1. Voice cloning</h4><p>You may clone a voice only from samples you own or have explicit consent to use (your own voice, or someone who has agreed in writing). Cloning someone's voice without their consent is prohibited and, in many jurisdictions, illegal.</p>
<h4>2. Disclosure to listeners</h4><p>When an Agent speaks or calls using a cloned or synthetic voice, the recipient must be informed they are interacting with an AI agent at the start of the interaction. Secretly passing off AI speech as a real person is prohibited.</p>
<h4>3. Calls & recording</h4><p>Call-recording and consent laws vary by country. You are responsible for obtaining any legally required consents before recording, and for identifying the calling party truthfully on every call.</p>
<h4>4. Where voice data lives</h4><p>Voice samples, transcripts and cloned models are stored only on your own server (via VoiceStudio) and are deleted permanently when you delete your account. We never receive, store, or train on your voice data.</p>
<h4>5. Agent autonomy limits</h4><p>Agents execute the intents they parse from your instructions. Review the Records page regularly; you are responsible for actions your Agents take. Marketing auto-posting only publishes to accounts you connected and within the daily limit you set.</p>
<h4>6. Revocation</h4><p>Delete an Agent or your account at any time to remove its voice, history and permissions immediately.</p>`],
billing: ["Billing & Refunds Policy", `<p><em>Last updated: November 2026.</em></p>
<h4>1. Current pricing</h4><p>The AgentHub MVP is currently provided free of charge during the preview period. No payment details are collected by us.</p>
<h4>2. Third-party costs</h4><p>You pay your own providers directly for services you connect (telephony, messaging, social APIs, LLM APIs, hosting). Their billing and refund terms apply.</p>
<h4>3. Future paid plans</h4><p>If paid plans are introduced, they will be billed in advance, cancellable anytime (access continues to the end of the paid period), and refundable within 14 days of first purchase if the Service has not been materially used. Changes will be announced in-app and on this page.</p>
<h4>4. Downgrades</h4><p>Deleting Agents reduces usage limits immediately; deleting your account ends all obligations.</p>`]
};
const POLICY_ALIASES = {"acceptable-use": "acceptable", "ai-policy": "ai"};
function viewPolicy(key) { key = POLICY_ALIASES[key] || key;
  const p = POLICIES[key]; if (!p) return location.hash = "#/";
  document.title = p[0] + " - AgentHub";
  $("#app").innerHTML = `<div class="panel policy"><h2>${p[0]}</h2>${p[1]}</div>`; }

function route() {
  const h = location.hash.slice(2) || "";
  const [path, qs] = h.split("?");
  document.title = "AgentHub";
  if (!path || path === "/") return viewHome();
  if (path === "login") return viewLogin();
  if (path === "forgot") return viewForgot();
  if (path === "reset") return viewReset(params.get("token") || "");
  if (path === "logout") { (async () => { try { await api("/api/auth/logout", { method: "POST" }); } catch {}
    state.user = null; chrome(); location.hash = "#/"; })(); return; }
  if (path === "register") return viewRegister();
  if (path === "account") return viewAccount();
  if (path === "agents") return viewAgents();
  if (path.startsWith("agent/")) return viewAgent(path.split("/")[1]);
  if (path === "tasks") return viewTasks();
  if (path === "posts") return viewPosts();
  if (path === "skills") return viewSkills();
  if (path === "leads") return viewLeads();
  if (["terms","privacy","cookies","acceptable-use","ai-policy","billing"].includes(path)) return viewPolicy(path);
  viewHome();
}
(async function boot() {
  try { state.user = await api("/api/auth/me"); } catch { state.user = null; }
  chrome(); route();
})();
window.addEventListener("hashchange", route);

/* ---------------- cookie consent banner ---------------- */
(function consentBanner() {
  const KEY = "ah_cookie_consent";
  const banner = document.getElementById("cookie-banner");
  if (!banner) return;
  if (!localStorage.getItem(KEY)) banner.hidden = false;
  const pick = v => { localStorage.setItem(KEY, v); banner.hidden = true; };
  const a = document.getElementById("cb-accept"), d = document.getElementById("cb-decline");
  if (a) a.onclick = () => pick("accepted");
  if (d) d.onclick = () => pick("declined");
})();

// IMIES dashboard — vanilla JS. Talks to the FastAPI endpoints and renders tabs.
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const esc = (s) => (s ?? "").toString().replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2600);
}
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
}
function prioBadge(p) {
  const k = (p || "").toLowerCase();
  const cls = k === "high" ? "high" : k === "medium" ? "medium" : "low";
  return `<span class="badge ${cls}">${esc(p || "—")}</span>`;
}
function sevBar(v) {
  const color = v >= 70 ? "var(--red)" : v >= 40 ? "var(--amber)" : "var(--green)";
  return `<div class="sev-bar"><div class="sev-fill" style="width:${v}%;background:${color}"></div></div>
          <span class="muted" style="font-size:11px">${v}</span>`;
}

// ---------- tabs ----------
$$(".tab").forEach(tab => tab.addEventListener("click", () => {
  $$(".tab").forEach(t => t.classList.remove("active"));
  $$(".tabpane").forEach(p => p.classList.remove("active"));
  tab.classList.add("active");
  $("#tab-" + tab.dataset.tab).classList.add("active");
  loadTab(tab.dataset.tab);
}));

function loadTab(name) {
  if (name === "escalations") renderEscalations();
  else if (name === "projects") renderProjects();
  else if (name === "tasks") renderTasks();
  else if (name === "meetings") renderMeetings();
  else if (name === "insights") renderInsights();
  else if (name === "graph") renderGraph();
}

// ---------- KPIs ----------
async function refreshKpis() {
  try {
    const ins = await api("/api/insights");
    $("#kpis").innerHTML = `
      <div class="kpi ${ins.open_escalations ? "alert" : ""}"><div class="v">${ins.open_escalations}</div><div class="l">Open escalations</div></div>
      <div class="kpi"><div class="v">${ins.open_tasks}</div><div class="l">Open tasks</div></div>
      <div class="kpi"><div class="v">${ins.projects_at_risk.length}</div><div class="l">Projects at risk</div></div>
      <div class="kpi"><div class="v">${ins.accountability_gaps}</div><div class="l">Owner gaps</div></div>
      <div class="kpi"><div class="v">${ins.duplicate_escalations}</div><div class="l">Duplicates</div></div>`;
  } catch (e) { /* DB may be empty */ }
}

// ---------- Escalations ----------
async function renderEscalations() {
  const pane = $("#tab-escalations");
  const rows = await api("/api/escalations");
  if (!rows.length) return pane.innerHTML = `<div class="empty">No escalations yet. Ingest a meeting to begin.</div>`;
  pane.innerHTML = `<table><thead><tr>
      <th>Severity</th><th>Escalation</th><th>Raised by</th><th>Project</th>
      <th>Priority</th><th>Teams</th><th>Source</th></tr></thead><tbody>
    ${rows.map(e => `<tr>
      <td style="white-space:nowrap">${sevBar(e.severity_score)}</td>
      <td>${esc(e.description)} ${e.is_duplicate ? '<span class="badge dup">duplicate</span>' : ""}</td>
      <td>${esc(e.raised_by || "—")}</td>
      <td>${esc(e.project || "—")}</td>
      <td>${prioBadge(e.priority)}</td>
      <td>${(e.teams || []).map(t => `<span class="badge team">${esc(t)}</span>`).join(" ") || "—"}</td>
      <td class="muted">${esc(e.meeting || "—")}</td></tr>`).join("")}
    </tbody></table>`;
}

// ---------- Projects ----------
async function renderProjects() {
  const pane = $("#tab-projects");
  const ins = await api("/api/insights");
  const h = ins.project_health;
  if (!h.length) return pane.innerHTML = `<div class="empty">No projects yet.</div>`;
  pane.innerHTML = `<div class="grid">${h.map(p => `
    <div class="pcard">
      <h3><span class="status-dot status-${p.status}"></span>${esc(p.project)}</h3>
      <div class="muted" style="text-transform:uppercase;font-size:11px;margin-bottom:8px">${p.status.replace("_", " ")}</div>
      <div>Open escalations: <b>${p.open_escalations}</b></div>
      <div>Open tasks: <b>${p.open_tasks}</b></div>
      <div>Risks: <b>${p.risks}</b> · Blockers: <b>${p.blockers}</b></div>
      <div style="margin-top:8px">Max severity ${sevBar(p.max_severity)}</div>
    </div>`).join("")}</div>`;
}

// ---------- Tasks ----------
async function renderTasks() {
  const pane = $("#tab-tasks");
  const rows = await api("/api/tasks");
  if (!rows.length) return pane.innerHTML = `<div class="empty">No tasks yet.</div>`;
  pane.innerHTML = `<table><thead><tr>
      <th>Task</th><th>Owner</th><th>Project</th><th>Deadline</th><th>Priority</th><th>Status</th></tr></thead><tbody>
    ${rows.map(t => `<tr>
      <td>${esc(t.description)}</td>
      <td>${t.owner ? esc(t.owner) : '<span class="badge dup">unassigned</span>'}</td>
      <td>${esc(t.project || "—")}</td>
      <td>${esc(t.deadline || "—")}</td>
      <td>${prioBadge(t.priority)}</td>
      <td>${esc(t.status)}</td></tr>`).join("")}
    </tbody></table>`;
}

// ---------- Meetings (raw transcript + what was extracted from it) ----------
async function renderMeetings() {
  const pane = $("#tab-meetings");
  const rows = await api("/api/meetings");
  if (!rows.length) return pane.innerHTML = `<div class="empty">No meetings yet. Ingest one on the left.</div>`;
  pane.innerHTML = rows.map(m => `
    <div class="mcard" data-id="${m.id}">
      <div class="mcard-head">
        <div>
          <h3>${esc(m.title)}</h3>
          <div class="mmeta">
            <span class="badge team">${esc(m.source_type)}</span>
            ${m.sentiment ? `<span class="badge team">sentiment: ${esc(m.sentiment)}</span>` : ""}
            ${m.urgency ? `<span class="badge ${m.urgency === "high" ? "high" : m.urgency === "medium" ? "medium" : "low"}">urgency: ${esc(m.urgency)}</span>` : ""}
            ${(m.participants || []).map(p => `<span class="badge team">${esc(p)}</span>`).join(" ")}
          </div>
        </div>
        <div class="mactions">
          <button class="ghost mtoggle">View transcript</button>
          <button class="ghost danger mdelete" title="Delete this meeting and all data from it">Delete</button>
        </div>
      </div>
      <div class="mbody"></div>
    </div>`).join("");
}

// Delete a meeting and everything extracted from it.
document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest(".mdelete");
  if (!btn) return;
  const card = btn.closest(".mcard");
  const title = card.querySelector("h3").textContent;
  if (!confirm(`Delete "${title}" and ALL data extracted from it (tasks, escalations, risks, decisions)?\n\nThis cannot be undone.`)) return;
  btn.disabled = true; btn.textContent = "Deleting...";
  try {
    const r = await api(`/api/meetings/${card.dataset.id}`, { method: "DELETE" });
    const rm = r.removed;
    toast(`Deleted "${r.title}" — ${rm.tasks} tasks, ${rm.escalations} escalations removed`);
    renderMeetings(); refreshKpis();
  } catch (e) {
    btn.disabled = false; btn.textContent = "Delete";
    toast("Delete failed: " + e.message);
  }
});

// Expand/collapse a meeting card -> fetch full detail incl. raw transcript.
document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest(".mtoggle");
  if (!btn) return;
  const card = btn.closest(".mcard");
  const body = card.querySelector(".mbody");
  if (card.classList.contains("open")) {
    card.classList.remove("open"); body.innerHTML = ""; btn.textContent = "View transcript";
    return;
  }
  btn.textContent = "Hide"; card.classList.add("open");
  body.innerHTML = `<span class="spinner"></span> Loading transcript...`;
  try {
    const d = await api(`/api/meetings/${card.dataset.id}`);
    const items = (label, arr, fmt) => arr && arr.length
      ? `<div class="section-title">${label} (${arr.length})</div>${arr.map(fmt).join("")}` : "";
    body.innerHTML = `
      <div class="split">
        <div>
          <div class="section-title">Raw ${esc(d.source_type)}</div>
          <pre class="transcript">${esc(d.raw_text || "(no raw text stored)")}</pre>
        </div>
        <div>
          ${d.summary ? `<div class="section-title">AI summary</div><div class="muted">${esc(d.summary)}</div>` : ""}
          ${items("Escalations", d.escalations, e => `<div class="xitem">🚩 ${esc(e.description)} ${prioBadge(e.priority)} <span class="muted">sev ${e.severity_score}</span>${e.is_duplicate ? ' <span class="badge dup">duplicate</span>' : ""}</div>`)}
          ${items("Tasks", d.tasks, t => `<div class="xitem">✅ ${esc(t.description)} ${prioBadge(t.priority)} <span class="muted">${esc(t.owner || "unassigned")}${t.deadline ? " · " + esc(t.deadline) : ""}</span></div>`)}
          ${items("Risks", d.risks, r => `<div class="xitem">⚠️ ${esc(r.description)} ${prioBadge(r.priority)}</div>`)}
          ${items("Blockers", d.blockers, b => `<div class="xitem">⛔ ${esc(b.description)}</div>`)}
          ${items("Decisions", d.decisions, x => `<div class="xitem">📌 ${esc(x.description)}${x.rationale ? ` <span class="muted">— ${esc(x.rationale)}</span>` : ""}</div>`)}
          ${items("Open questions", d.open_questions, q => `<div class="xitem">❓ ${esc(q.question)}${q.project ? ` <span class="muted">(${esc(q.project)})</span>` : ""}</div>`)}
          ${items("Follow-ups / next steps", d.follow_ups, f => `<div class="xitem">➡️ ${esc(f.description)}${f.owner ? ` <span class="muted">— ${esc(f.owner)}</span>` : ""}</div>`)}
        </div>
      </div>`;
  } catch (e) { body.innerHTML = `<span style="color:var(--red)">${esc(e.message)}</span>`; }
});

// ---------- Insights ----------
async function renderInsights() {
  const pane = $("#tab-insights");
  const ins = await api("/api/insights");
  const workload = Object.entries(ins.workload).sort((a, b) => b[1] - a[1]);
  const maxW = Math.max(1, ...workload.map(w => w[1]));
  const maxT = Math.max(1, ...ins.escalation_trend.map(t => t.count));

  pane.innerHTML = `
    <div class="section-title">Team workload (open tasks per owner)</div>
    ${workload.length ? workload.map(([n, c]) => `
      <div class="bar-row"><div class="name">${esc(n)}</div>
        <div class="bar-track"><div class="bar-val" style="width:${(c / maxW) * 100}%"></div></div>
        <div class="num">${c}</div></div>`).join("") : '<div class="muted">No tasks.</div>'}

    <div class="section-title">Escalation trend</div>
    ${ins.escalation_trend.length ? `<div style="display:flex;align-items:flex-end;gap:10px;height:132px;padding:4px 2px">
      ${ins.escalation_trend.map(t => `<div style="text-align:center;width:46px;flex:0 0 auto" title="${esc(t.date)}: ${t.count}">
        <div style="font:600 11px var(--mono);color:var(--accent);margin-bottom:4px">${t.count}</div>
        <div style="background:linear-gradient(180deg,var(--accent),var(--accent-2));border-radius:5px 5px 0 0;height:${Math.max(6,(t.count / maxT) * 92)}px;box-shadow:0 0 14px -3px var(--accent-glow)"></div>
        <div class="muted" style="font:500 10px var(--mono);margin-top:6px">${esc(t.date.slice(5))}</div></div>`).join("")}
      </div>` : '<div class="muted">No escalations.</div>'}

    <div class="section-title">Top risks</div>
    ${ins.top_risks.length ? `<table><tbody>${ins.top_risks.map(r => `<tr>
        <td style="width:120px">${sevBar(r.severity_score)}</td>
        <td>${esc(r.description)}</td><td class="muted">${esc(r.project || "—")}</td></tr>`).join("")}</tbody></table>`
      : '<div class="muted">No risks.</div>'}

    <div class="section-title">Cross-team dependency map</div>
    ${ins.dependency_map.length ? ins.dependency_map.map(d => `
      <div style="margin:4px 0"><b>${esc(d.project)}</b> → ${d.teams.map(t => `<span class="badge team">${esc(t)}</span>`).join(" ")}</div>`).join("")
      : '<div class="muted">No cross-team dependencies recorded.</div>'}`;
}

// ---------- Graph (3-column layered layout: People -> Activity -> Projects) ----------
async function renderGraph() {
  const pane = $("#tab-graph");
  const g = await api("/api/graph");
  if (!g.nodes.length) return pane.innerHTML = `<div class="empty">No relationships yet.</div>`;

  const color = { person: "#5b9dff", project: "#7c5cff", task: "#35d07f", escalation: "#ff5c6c" };
  const trunc = (s, n) => (s && s.length > n) ? s.slice(0, n - 1) + "…" : (s || "");

  // Three columns so labels never stack on top of each other.
  const people = g.nodes.filter(n => n.type === "person");
  const activity = g.nodes.filter(n => n.type === "task" || n.type === "escalation");
  const projects = g.nodes.filter(n => n.type === "project");

  const W = Math.max(820, (pane.clientWidth || 900));
  const gap = 42, padY = 44;
  const rows = Math.max(people.length, activity.length, projects.length, 1);
  const H = Math.max(420, rows * gap + padY * 2);

  // Column x-positions. People labels go left, project labels go right, activity centered.
  const colX = { person: 150, activity: Math.round(W / 2), project: W - 150 };
  const pos = {};
  const place = (arr, x) => {
    const startY = (H - (arr.length - 1) * gap) / 2;
    arr.forEach((n, i) => { pos[n.id] = { x, y: startY + i * gap, node: n }; });
  };
  place(people, colX.person);
  place(activity, colX.activity);
  place(projects, colX.project);

  // Smooth horizontal bezier edges read cleaner than straight crossing lines.
  // data-source/data-target let us highlight an edge when either endpoint is hovered.
  const edges = g.edges.map(e => {
    const a = pos[e.source], b = pos[e.target];
    if (!a || !b) return "";
    const mx = (a.x + b.x) / 2;
    return `<path class="gedge" data-source="${esc(e.source)}" data-target="${esc(e.target)}"
            d="M ${a.x} ${a.y} C ${mx} ${a.y}, ${mx} ${b.y}, ${b.x} ${b.y}" fill="none"/>`;
  }).join("");

  // anchor: "left" => text to the left of node; "right" => to the right; "mid" => above.
  const drawNode = (p, anchor) => {
    const n = p.node;
    let tx = p.x, ta = "middle", ty = p.y + 4;
    if (anchor === "left") { tx = p.x - 13; ta = "end"; }
    else if (anchor === "right") { tx = p.x + 13; ta = "start"; }
    else { ty = p.y - 12; }   // activity labels sit just above their dot
    const max = anchor === "mid" ? 26 : 20;
    return `<g class="gnode" data-id="${esc(n.id)}">
      <title>${esc(n.label)}</title>
      <circle cx="${p.x}" cy="${p.y}" r="7" fill="${color[n.type] || "#888"}"/>
      <text x="${tx}" y="${ty}" fill="#c7d0e0" font-size="11" text-anchor="${ta}">${esc(trunc(n.label, max))}</text>
    </g>`;
  };

  const nodesSvg =
    people.map(n => drawNode(pos[n.id], "left")).join("") +
    activity.map(n => drawNode(pos[n.id], "mid")).join("") +
    projects.map(n => drawNode(pos[n.id], "right")).join("");

  // Column headers.
  const headers = `
    <text x="${colX.person}" y="22" fill="#8a97ad" font-size="11" text-anchor="middle" letter-spacing="1">PEOPLE</text>
    <text x="${colX.activity}" y="22" fill="#8a97ad" font-size="11" text-anchor="middle" letter-spacing="1">ACTIVITY</text>
    <text x="${colX.project}" y="22" fill="#8a97ad" font-size="11" text-anchor="middle" letter-spacing="1">PROJECTS</text>`;

  pane.innerHTML = `
    <div class="muted" style="margin-bottom:8px">
      <span style="color:#5b9dff">●</span> person &nbsp;
      <span style="color:#35d07f">●</span> task &nbsp;
      <span style="color:#ff5c6c">●</span> escalation &nbsp;
      <span style="color:#7c5cff">●</span> project
      <span class="ghint" style="float:right;font-size:12px">hover to trace · click to pin a node's connections</span>
    </div>
    <div class="graph-scroll"><svg width="${W}" height="${H}">${headers}${edges}${nodesSvg}</svg></div>`;

  // ---- interaction: hover previews connections; click PINS them ----
  const svg = pane.querySelector("svg");
  const hint = pane.querySelector(".ghint");
  const allEdges = [...svg.querySelectorAll(".gedge")];
  const allNodes = [...svg.querySelectorAll(".gnode")];
  let pinnedId = null;   // the currently pinned node, or null

  const labelOf = (id) => {
    const n = allNodes.find(nd => nd.dataset.id === id);
    return n ? n.querySelector("title").textContent : id;
  };

  function applyFocus(id) {
    clearClasses();
    const neighbours = new Set([id]);
    allEdges.forEach(ed => {
      if (ed.dataset.source === id || ed.dataset.target === id) {
        ed.classList.add("hl");
        neighbours.add(ed.dataset.source);
        neighbours.add(ed.dataset.target);
      } else {
        ed.classList.add("dim");
      }
    });
    allNodes.forEach(nd => nd.classList.add(neighbours.has(nd.dataset.id) ? "hl" : "dim"));
    if (pinnedId) {
      const pn = allNodes.find(nd => nd.dataset.id === pinnedId);
      if (pn) pn.classList.add("pinned");
    }
  }
  function clearClasses() {
    allEdges.forEach(ed => ed.classList.remove("hl", "dim"));
    allNodes.forEach(nd => nd.classList.remove("hl", "dim", "pinned"));
  }
  // Restore to whatever should be showing when the mouse isn't over a node.
  function rest() {
    if (pinnedId) { applyFocus(pinnedId); }
    else { clearClasses(); hint.textContent = "hover to trace · click to pin a node's connections"; }
  }

  allNodes.forEach(nd => {
    nd.addEventListener("mouseenter", () => applyFocus(nd.dataset.id));
    nd.addEventListener("mouseleave", rest);
    nd.addEventListener("click", (ev) => {
      ev.stopPropagation();              // don't let the svg-background handler unpin
      const id = nd.dataset.id;
      pinnedId = (pinnedId === id) ? null : id;   // toggle
      if (pinnedId) {
        applyFocus(pinnedId);
        hint.innerHTML = `📌 pinned: <b>${esc(labelOf(pinnedId))}</b> — click it again or click empty space to unpin`;
      } else {
        rest();
      }
    });
  });
  // Clicking empty graph space clears the pin.
  svg.addEventListener("click", () => { pinnedId = null; rest(); });
}

// ---------- Ingest ----------
$("#ingestBtn").addEventListener("click", async () => {
  const text = $("#ingestText").value.trim();
  if (!text) return toast("Paste some meeting text first.");
  const btn = $("#ingestBtn"); btn.disabled = true;
  $("#ingestResult").innerHTML = `<span class="spinner"></span> Extracting...`;
  try {
    const r = await api("/api/ingest", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, title: $("#ingestTitle").value || null }),
    });
    const c = r.counts;
    $("#ingestResult").innerHTML = `
      <div class="muted">Extracted from <b>${esc(r.title)}</b>
        · sentiment <b>${esc(r.sentiment || "—")}</b> · urgency <b>${esc(r.urgency || "—")}</b></div>
      <div style="margin-top:6px">
        ${Object.entries(c).map(([k, v]) => `<span class="badge team">${v} ${k}</span>`).join(" ")}
      </div>`;
    toast("Meeting ingested ✓");
    refreshKpis(); loadTab($(".tab.active").dataset.tab);
  } catch (e) { $("#ingestResult").innerHTML = `<span style="color:var(--red)">${esc(e.message)}</span>`; }
  finally { btn.disabled = false; }
});

$("#fileInput").addEventListener("change", async (ev) => {
  const file = ev.target.files[0]; if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  $("#ingestResult").innerHTML = `<span class="spinner"></span> Reading ${esc(file.name)}...`;
  try {
    // Load the file's text into the editor — the user reviews, then clicks Extract.
    const r = await api("/api/extract-text", { method: "POST", body: fd });
    $("#ingestText").value = r.text;
    if (!$("#ingestTitle").value) $("#ingestTitle").value = r.filename.replace(/\.[^.]+$/, "");
    $("#ingestResult").innerHTML =
      `<div class="muted">Loaded <b>${esc(r.filename)}</b> (${r.text.length} chars) into the box.
       Review it, then click <b>Extract intelligence</b>.</div>`;
    toast("File text loaded ✓");
  } catch (e) { $("#ingestResult").innerHTML = `<span style="color:var(--red)">${esc(e.message)}</span>`; }
  finally { ev.target.value = ""; }   // reset so the same file can be re-selected
});

// ---------- Speech-to-text (browser-native Web Speech API; no server, no key) ----------
(function setupSpeech() {
  const micBtn = $("#micBtn"), status = $("#micStatus"), ta = $("#ingestText");
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {                                   // Firefox / unsupported
    micBtn.disabled = true;
    micBtn.textContent = "🎤 n/a";
    micBtn.title = "Speech recognition needs Chrome or Edge";
    status.textContent = "Voice input needs Chrome or Edge.";
    return;
  }
  const rec = new SR();
  rec.continuous = true;        // keep listening across pauses
  rec.interimResults = true;    // show words live as you speak
  rec.lang = "en-US";
  let listening = false, baseText = "", finalText = "";

  micBtn.addEventListener("click", () => {
    if (listening) { rec.stop(); return; }
    // Append to whatever is already in the box.
    baseText = ta.value ? ta.value.replace(/\s*$/, "") + " " : "";
    finalText = "";
    try { rec.start(); } catch (_) { /* ignore double-start */ }
  });

  rec.onstart = () => {
    listening = true;
    micBtn.classList.add("recording");
    micBtn.textContent = "⏹ Stop";
    status.textContent = "🎙️ Listening… speak now";
  };
  rec.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += t + " ";
      else interim += t;
    }
    ta.value = baseText + finalText + interim;   // live update
  };
  rec.onerror = (e) => {
    status.textContent = e.error === "not-allowed"
      ? "Microphone blocked — allow mic access for this site."
      : "Mic error: " + e.error;
  };
  rec.onend = () => {
    listening = false;
    micBtn.classList.remove("recording");
    micBtn.textContent = "🎤 Speak";
    if (!status.textContent.startsWith("Mic") && !status.textContent.startsWith("Voice"))
      status.textContent = finalText ? "✓ Captured. Edit if needed, then Extract intelligence." : "";
  };
})();

// ---------- Query ----------
async function runQuery(q) {
  $("#queryInput").value = q;
  $("#queryResult").innerHTML = `<span class="spinner"></span> Thinking...`;
  try {
    const r = await api("/api/query", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    $("#queryResult").innerHTML = `
      <div class="markdown" style="padding:12px 14px">${esc(r.answer).replace(/\n/g, "<br>")}</div>
      ${r.sources.length ? `<div class="muted" style="margin-top:6px">Sources: ${r.sources.map(esc).join(" · ")}</div>` : ""}`;
  } catch (e) { $("#queryResult").innerHTML = `<span style="color:var(--red)">${esc(e.message)}</span>`; }
}
$("#queryBtn").addEventListener("click", () => {
  const q = $("#queryInput").value.trim(); if (q) runQuery(q);
});
$("#queryInput").addEventListener("keydown", e => { if (e.key === "Enter") $("#queryBtn").click(); });
$$("#exampleQs span").forEach(s => s.addEventListener("click", () => runQuery(s.dataset.q)));

// ---------- Report tab ----------
$("#tab-report").innerHTML = `
  <button id="reportBtn" class="primary">Generate leadership action report</button>
  <div id="reportOut" style="margin-top:14px"></div>`;
document.addEventListener("click", async (e) => {
  if (e.target.id !== "reportBtn") return;
  $("#reportOut").innerHTML = `<span class="spinner"></span> Drafting report...`;
  try {
    const r = await api("/api/report", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope: "org" }),
    });
    $("#reportOut").innerHTML = `<div class="markdown">${mdToHtml(r.report)}</div>`;
  } catch (err) { $("#reportOut").innerHTML = `<span style="color:var(--red)">${esc(err.message)}</span>`; }
});

// Tiny markdown -> HTML (headings, bold, lists).
function mdToHtml(md) {
  return esc(md)
    .replace(/^### (.*)$/gm, "<h3>$1</h3>")
    .replace(/^## (.*)$/gm, "<h2>$1</h2>")
    .replace(/^# (.*)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/^[-*] (.*)$/gm, "• $1")
    .replace(/\n/g, "<br>");
}

// ---------- init ----------
refreshKpis();
renderEscalations();

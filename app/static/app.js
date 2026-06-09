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
    ${ins.escalation_trend.length ? `<div style="display:flex;align-items:flex-end;gap:8px;height:120px">
      ${ins.escalation_trend.map(t => `<div style="text-align:center;flex:1">
        <div style="background:linear-gradient(180deg,var(--accent),var(--accent-2));border-radius:4px 4px 0 0;height:${(t.count / maxT) * 100}px"></div>
        <div class="muted" style="font-size:10px;margin-top:4px">${esc(t.date.slice(5))}</div></div>`).join("")}
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

// ---------- Graph (simple circular layout SVG) ----------
async function renderGraph() {
  const pane = $("#tab-graph");
  const g = await api("/api/graph");
  if (!g.nodes.length) return pane.innerHTML = `<div class="empty">No relationships yet.</div>`;
  const W = pane.clientWidth || 900, H = 560, cx = W / 2, cy = H / 2;
  const R = Math.min(W, H) / 2 - 70;
  const pos = {};
  g.nodes.forEach((n, i) => {
    const a = (i / g.nodes.length) * Math.PI * 2;
    pos[n.id] = { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) };
  });
  const color = { person: "#5b9dff", project: "#7c5cff", task: "#35d07f", escalation: "#ff5c6c" };
  const edges = g.edges.map(e => {
    const a = pos[e.source], b = pos[e.target];
    if (!a || !b) return "";
    return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#2b3650" stroke-width="1.2"/>`;
  }).join("");
  const nodes = g.nodes.map(n => {
    const p = pos[n.id];
    return `<g>
      <circle cx="${p.x}" cy="${p.y}" r="8" fill="${color[n.type] || "#888"}"/>
      <text x="${p.x + 11}" y="${p.y + 4}" fill="#cdd6e6" font-size="11">${esc(n.label)}</text>
    </g>`;
  }).join("");
  pane.innerHTML = `
    <div class="muted" style="margin-bottom:8px">
      <span style="color:#5b9dff">●</span> person
      <span style="color:#7c5cff">●</span> project
      <span style="color:#35d07f">●</span> task
      <span style="color:#ff5c6c">●</span> escalation
    </div>
    <svg id="graph" viewBox="0 0 ${W} ${H}">${edges}${nodes}</svg>`;
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
    const r = await api("/api/ingest/file", { method: "POST", body: fd });
    toast(`Ingested ${esc(r.title)} ✓`); refreshKpis(); loadTab($(".tab.active").dataset.tab);
    $("#ingestResult").innerHTML = `<div class="muted">Ingested <b>${esc(r.title)}</b></div>`;
  } catch (e) { $("#ingestResult").innerHTML = `<span style="color:var(--red)">${esc(e.message)}</span>`; }
});

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

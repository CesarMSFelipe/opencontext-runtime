// OpenContext Studio — minimal vanilla client over the read-only JSON API.
// Fetches GET endpoints only; 3s poll for the live dashboard (matches the TUI
// cockpit poll). This is an honest MVP shell, not a rich SPA.
"use strict";

const VIEWS = [
  "dashboard",
  "timeline",
  "timelines",
  "context",
  "kg",
  "memory",
  "receipts",
  "harness",
  "cost",
  "decisions",
  "brain",
  "cache",
  "learning",
];
const GLOBAL_VIEWS = ["capabilities", "config"];

let activeSession = null;
let activeView = "dashboard";
let pollTimer = null;

async function getJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function setStatus(text) {
  document.getElementById("status").textContent = text;
}

function renderPanel(data) {
  document.getElementById("panel").textContent = JSON.stringify(data, null, 2);
}

async function loadSessions() {
  try {
    const sessions = await getJSON("/api/sessions");
    const ul = document.getElementById("sessions");
    ul.innerHTML = "";
    sessions.forEach((s) => {
      const li = document.createElement("li");
      if (s.id === activeSession) li.className = "active";
      li.innerHTML =
        `<div class="task">${s.task || s.id}</div>` +
        `<div class="meta">${s.kind} · ${s.status} · ${s.current_node || "-"}</div>`;
      li.onclick = () => selectSession(s.id);
      ul.appendChild(li);
    });
    setStatus(`${sessions.length} session(s)`);
  } catch (err) {
    setStatus(`error: ${err.message}`);
  }
}

function renderViewNav() {
  const nav = document.getElementById("views");
  nav.innerHTML = "";
  const all = activeSession ? VIEWS.concat(GLOBAL_VIEWS) : GLOBAL_VIEWS;
  all.forEach((v) => {
    const b = document.createElement("button");
    b.textContent = v;
    if (v === activeView) b.className = "active";
    b.onclick = () => selectView(v);
    nav.appendChild(b);
  });
}

async function refreshView() {
  try {
    if (GLOBAL_VIEWS.includes(activeView)) {
      renderPanel(await getJSON(`/api/${activeView}`));
    } else if (!activeSession) {
      renderPanel("Select a session.");
    } else if (activeView === "dashboard") {
      renderPanel(await getJSON(`/api/sessions/${activeSession}`));
    } else {
      renderPanel(await getJSON(`/api/sessions/${activeSession}/${activeView}`));
    }
  } catch (err) {
    renderPanel(`error: ${err.message}`);
  }
}

function selectSession(id) {
  activeSession = id;
  if (!VIEWS.includes(activeView) && !GLOBAL_VIEWS.includes(activeView)) {
    activeView = "dashboard";
  }
  loadSessions();
  renderViewNav();
  refreshView();
}

function selectView(v) {
  activeView = v;
  renderViewNav();
  refreshView();
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => {
    loadSessions();
    if (activeView === "dashboard" || activeView === "timeline") refreshView();
  }, 3000);
}

renderViewNav();
loadSessions();
startPolling();

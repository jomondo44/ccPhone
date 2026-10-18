"use strict";
// Indie Musician Admin Lite: single-page UI. No frameworks, works offline.

const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const today = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD local
const fmtDate = (d) => {
  if (!d) return "";
  const dt = new Date(d + "T00:00:00");
  return isNaN(dt) ? d : dt.toLocaleDateString(undefined,
    { month: "short", day: "numeric", year: "numeric" });
};
const daysFrom = (d) => d ? Math.round(
  (new Date(d + "T00:00:00") - new Date(today() + "T00:00:00")) / 864e5) : null;
const pct = (n) => `${Math.round((+n || 0) * 100) / 100}%`;

// ---------- API ----------
async function api(path, opts = {}) {
  const res = await fetch("/api/" + path, {
    method: opts.method || "GET",
    headers: opts.body ? { "Content-Type": "application/json" } : {},
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
const list = (t, q = {}) => api(t + (Object.keys(q).length ? "?" + new URLSearchParams(q) : ""));
const get = (t, id) => api(`${t}/${id}`);
const create = (t, body) => api(t, { method: "POST", body });
const update = (t, id, body) => api(`${t}/${id}`, { method: "PUT", body });
const remove = (t, id) => api(`${t}/${id}`, { method: "DELETE" });

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 2200);
}

// ---------- form specs ----------
const OPT = {
  releaseKind: ["Single", "EP", "Album", "Remix", "Music video", "Other"],
  releaseStatus: ["Planning", "Recording", "Mixing", "Mastering", "Scheduled", "Released", "On hold"],
  role: ["Artist", "Songwriter", "Producer", "Co-writer", "Featured artist", "Engineer",
    "Mix engineer", "Mastering engineer", "Musician", "Manager", "Label", "Publisher",
    "Designer", "Videographer", "Publicist", "Other"],
  pro: ["", "ASCAP", "BMI", "SESAC", "GMR", "SOCAN", "PRS", "APRA AMCOS", "GEMA", "SACEM", "Other", "None"],
  method: ["Call", "Text", "Email", "DM", "In person", "Session", "Other"],
  promoKind: ["Playlist", "Blog", "Radio", "Podcast", "Press", "Influencer", "Ad", "Live session", "Other"],
  promoStatus: ["To pitch", "Pitched", "Followed up", "Accepted", "Published", "Declined", "No reply"],
};

const SPECS = {
  releases: { name: "Release", fields: [
    ["title", "Title", "text", { required: true }],
    ["artist", "Artist name", "text"],
    ["kind", "Type", "select", { options: OPT.releaseKind }],
    ["release_date", "Release date", "date"],
    ["status", "Status", "select", { options: OPT.releaseStatus }],
    ["distributor", "Distributor", "text"],
    ["upc", "UPC", "text"],
    ["notes", "Notes", "textarea"],
  ]},
  songs: { name: "Song", fields: [
    ["title", "Song title", "text", { required: true }],
    ["release_id", "Release", "release"],
    ["isrc", "ISRC", "text"],
    ["date_written", "Date written", "date"],
    ["studio", "Studio / location", "text"],
    ["notes", "Notes", "textarea"],
  ]},
  splits: { name: "Split", fields: [
    ["collaborator_id", "Pick from collaborators (fills details)", "collab"],
    ["name", "Legal name", "text", { required: true }],
    ["role", "Role", "select", { options: OPT.role }],
    ["writer_pct", "Writer share %", "number"],
    ["publisher", "Publisher", "text"],
    ["pub_pct", "Publishing share %", "number"],
    ["master_pct", "Master share %", "number"],
    ["pro", "PRO", "select", { options: OPT.pro }],
    ["ipi", "IPI / CAE #", "text"],
    ["signed", "Signed the split sheet", "check"],
  ]},
  collaborators: { name: "Collaborator", fields: [
    ["name", "Name", "text", { required: true }],
    ["role", "Main role", "select", { options: OPT.role }],
    ["email", "Email", "email"],
    ["phone", "Phone", "tel"],
    ["pro", "PRO", "select", { options: OPT.pro }],
    ["ipi", "IPI / CAE #", "text"],
    ["publisher", "Publisher", "text"],
    ["socials", "Socials / website", "text"],
    ["notes", "Notes (rates, payment info, vibe)", "textarea"],
  ]},
  contact_log: { name: "Contact", fields: [
    ["date", "Date", "date"],
    ["method", "How", "select", { options: OPT.method }],
    ["note", "What happened / next step", "textarea"],
  ]},
  promos: { name: "Promo", fields: [
    ["outlet", "Outlet / playlist / show", "text", { required: true }],
    ["kind", "Type", "select", { options: OPT.promoKind }],
    ["release_id", "For release", "release"],
    ["contact", "Contact name", "text"],
    ["email", "Email / handle", "text"],
    ["status", "Status", "select", { options: OPT.promoStatus }],
    ["pitched_on", "Pitched on", "date"],
    ["follow_up", "Follow up on", "date"],
    ["cost", "Cost ($)", "number"],
    ["result_link", "Result link", "url"],
    ["notes", "Notes", "textarea"],
  ]},
  checklist: { name: "Task", fields: [
    ["task", "Task", "text", { required: true }],
    ["due_date", "Due date", "date"],
    ["done", "Done", "check"],
  ]},
};

// Opens a modal form. Resolves with the saved row, "deleted", or null.
async function openForm(table, row = {}, defaults = {}) {
  const spec = SPECS[table];
  const isEdit = !!row.id;
  const data = { ...defaults, ...row };
  const needsReleases = spec.fields.some((f) => f[2] === "release");
  const needsCollabs = spec.fields.some((f) => f[2] === "collab");
  const [releases, collabs] = await Promise.all([
    needsReleases ? list("releases") : [], needsCollabs ? list("collaborators") : []]);

  const fieldHtml = ([key, label, type, o = {}]) => {
    const v = data[key] ?? "";
    const id = "f_" + key;
    const req = o.required ? "required" : "";
    if (type === "check") {
      return `<div class="field check"><label><input type="checkbox" id="${id}" name="${key}" ${v ? "checked" : ""}>${esc(label)}</label></div>`;
    }
    let input;
    if (type === "select") {
      const opts = o.options.includes(v) || v === "" ? o.options : [v, ...o.options];
      input = `<select id="${id}" name="${key}">${opts.map((x) =>
        `<option ${x === v ? "selected" : ""} value="${esc(x)}">${esc(x || "-")}</option>`).join("")}</select>`;
    } else if (type === "release" || type === "collab") {
      const src = type === "release" ? releases : collabs;
      const lbl = type === "release" ? (r) => r.title : (c) => `${c.name}${c.role ? " (" + c.role + ")" : ""}`;
      input = `<select id="${id}" name="${key}"><option value="">- none -</option>${src.map((r) =>
        `<option value="${r.id}" ${+v === r.id ? "selected" : ""}>${esc(lbl(r))}</option>`).join("")}</select>`;
    } else if (type === "textarea") {
      input = `<textarea id="${id}" name="${key}">${esc(v)}</textarea>`;
    } else {
      const extra = type === "number" ? 'step="any" inputmode="decimal"' : "";
      input = `<input id="${id}" name="${key}" type="${type}" value="${esc(v)}" ${req} ${extra}>`;
    }
    return `<div class="field"><label for="${id}">${esc(label)}</label>${input}</div>`;
  };

  const form = $("#modal-form");
  form.innerHTML = `<h3>${isEdit ? "Edit" : "New"} ${spec.name.toLowerCase()}</h3>
    ${spec.fields.map(fieldHtml).join("")}
    <div class="actions">
      ${isEdit ? '<button type="button" class="btn danger" data-act="delete">Delete</button>' : ""}
      <span class="spacer"></span>
      <button type="button" class="btn" data-act="cancel">Cancel</button>
      <button type="submit" class="btn primary">Save</button>
    </div>`;

  // Picking a collaborator autofills the split row.
  const pick = $("#f_collaborator_id", form);
  if (pick) pick.addEventListener("change", () => {
    const c = collabs.find((x) => x.id === +pick.value);
    if (!c) return;
    for (const k of ["name", "pro", "ipi", "publisher"]) {
      const el = $("#f_" + k, form);
      if (el && c[k]) el.value = c[k];
    }
    const role = $("#f_role", form);
    if (role && c.role) role.value = c.role;
  });

  const dlg = $("#modal");
  dlg.showModal();
  $("input,select,textarea", form)?.focus();

  return new Promise((resolve) => {
    const done = (val) => { dlg.close(); form.onsubmit = form.onclick = null; resolve(val); };
    form.onclick = async (e) => {
      const act = e.target.dataset.act;
      if (act === "cancel") done(null);
      if (act === "delete" && confirm(`Delete this ${spec.name.toLowerCase()}?`)) {
        await remove(table, row.id);
        toast("Deleted");
        done("deleted");
      }
    };
    form.onsubmit = async (e) => {
      e.preventDefault();
      const body = {};
      for (const [key, , type] of spec.fields) {
        const el = form.elements[key];
        if (type === "check") body[key] = el.checked ? 1 : 0;
        else if (type === "number") body[key] = el.value === "" ? 0 : +el.value;
        else body[key] = el.value;
      }
      try {
        const saved = isEdit ? await update(table, row.id, body)
          : await create(table, { ...defaults, ...body });
        toast("Saved");
        done(saved);
      } catch (err) { toast(err.message); }
    };
    dlg.oncancel = () => done(null);
  });
}

// ---------- shell / routing ----------
let addAction = null;
function shell(title, { back = false, add = null } = {}) {
  $("#title").textContent = title;
  document.title = title === "Indie Admin Lite" ? title : `${title} - Indie Admin Lite`;
  $("#back").hidden = !back;
  addAction = add;
  $("#add").hidden = !add;
}
$("#back").onclick = () => history.length > 1 ? history.back() : (location.hash = "#/home");
$("#add").onclick = () => addAction && addAction();

const routes = {
  home: viewHome, releases: viewReleases, release: viewRelease,
  songs: viewSongs, song: viewSong, people: viewPeople, person: viewPerson,
  promo: viewPromo,
};
const tabOf = { release: "releases", song: "songs", person: "people" };

async function render() {
  const [, name = "home", id] = location.hash.split("/");
  const fn = routes[name] || viewHome;
  document.querySelectorAll(".tabs a").forEach((a) =>
    a.classList.toggle("on", a.dataset.tab === (tabOf[name] || name)));
  try {
    await fn(id && +id);
  } catch (err) {
    view.innerHTML = `<div class="card"><b>Something went wrong.</b><p class="muted">${esc(err.message)}</p>
      <p class="muted">Is the server still running in Termux?</p></div>`;
  }
}
window.addEventListener("hashchange", () => { render(); window.scrollTo(0, 0); });
const go = (h) => { location.hash = h; };
const reload = () => render();

// Delegated click handling for list rows and inline actions.
view.addEventListener("click", (e) => {
  const link = e.target.closest("[data-go]");
  if (link && !e.target.closest("input,button,a")) go(link.dataset.go);
});

function dueChip(d, done = false) {
  if (!d) return "";
  const n = daysFrom(d);
  const cls = done ? "" : n < 0 ? "bad" : n <= 3 ? "warn" : "";
  const txt = n === 0 ? "today" : n === 1 ? "tomorrow" : n === -1 ? "yesterday"
    : n < 0 ? `${-n}d late` : n <= 60 ? `in ${n}d` : `in ${Math.round(n / 7)}w`;
  return `<span class="chip ${cls}">${txt}</span>`;
}
const statusCls = (s) => ({
  Released: "ok", Accepted: "ok", Published: "ok", Declined: "bad", "No reply": "bad",
  "On hold": "warn", "Followed up": "warn", Pitched: "warn",
}[s] || "");

// ---------- Home ----------
async function viewHome() {
  shell("Indie Admin Lite");
  const d = await api("dashboard");
  const upcoming = d.releases.filter((r) => r.status !== "Released");
  view.innerHTML = `
    <div class="stats">
      <div class="stat"><b>${upcoming.length}</b><small>active releases</small></div>
      <div class="stat"><b>${d.tasks.length}</b><small>tasks due ≤7d</small></div>
      <div class="stat"><b>${d.follow_ups.length}</b><small>follow-ups</small></div>
    </div>
    <div class="card"><h2>Releases</h2>
      ${d.releases.length ? `<ul class="list">${d.releases.map((r) => `
        <li class="row-link" data-go="#/release/${r.id}"><div class="grow">
          <div><b>${esc(r.title)}</b> <span class="chip ${statusCls(r.status)}">${esc(r.status)}</span></div>
          <div class="sub">${esc(r.kind)}${r.release_date ? " · " + fmtDate(r.release_date) : ""} · ${r.done}/${r.total} tasks</div>
          <div class="bar"><i style="width:${r.total ? (100 * r.done / r.total) : 0}%"></i></div>
        </div>${dueChip(r.release_date, r.status === "Released")}</li>`).join("")}</ul>`
        : `<p class="empty">No releases yet.<br><a href="#/releases">Plan your first release</a></p>`}
    </div>
    <div class="card"><h2>Due this week</h2>
      ${d.tasks.length ? `<ul class="list">${d.tasks.map((t) => `
        <li><input type="checkbox" data-task="${t.id}">
        <div class="grow row-link" data-go="#/release/${t.release_id}"><div>${esc(t.task)}</div>
        <div class="sub">${esc(t.release_title)}</div></div>${dueChip(t.due_date)}</li>`).join("")}</ul>`
        : `<p class="empty">Nothing due. Nice.</p>`}
    </div>
    <div class="card"><h2>Promo follow-ups</h2>
      ${d.follow_ups.length ? `<ul class="list">${d.follow_ups.map((p) => `
        <li class="row-link" data-promo="${p.id}"><div class="grow"><div>${esc(p.outlet)}</div>
        <div class="sub">${esc(p.kind)} · ${esc(p.status)}${p.release_title ? " · " + esc(p.release_title) : ""}</div></div>
        ${dueChip(p.follow_up)}</li>`).join("")}</ul>`
        : `<p class="empty">No follow-ups due.</p>`}
    </div>
    <div class="card"><h2>Splits needing attention</h2>
      ${d.split_issues.length ? `<ul class="list">${d.split_issues.map((s) => `
        <li class="row-link" data-go="#/song/${s.id}"><div class="grow"><div>${esc(s.title)}</div>
        <div class="sub">${s.n === 0 ? "No writers added" :
          Math.abs(s.writer_total - 100) > 0.01 ? `Writer shares total ${pct(s.writer_total)}` :
          `${s.n - s.signed} unsigned`}</div></div><span class="chip warn">fix</span></li>`).join("")}</ul>`
        : `<p class="empty">All split sheets add up and are signed.</p>`}
    </div>
    <div class="card"><h2>Backup & export</h2>
      <p class="muted">Everything is stored on this phone only. Back up before switching phones.</p>
      <a class="btn" href="/api/export" download>Download backup (.json)</a>
      <label class="btn">Restore backup<input id="restore" type="file" accept=".json,application/json" hidden></label>
      <div class="muted" style="margin-top:8px">CSV:
        <a href="/api/csv/collaborators" download>collaborators</a> ·
        <a href="/api/csv/splits" download>splits</a> ·
        <a href="/api/csv/promos" download>promo</a> ·
        <a href="/api/csv/releases" download>releases</a></div>
    </div>`;

  view.querySelectorAll("[data-task]").forEach((cb) => cb.onchange = async () => {
    await update("checklist", cb.dataset.task, { done: cb.checked ? 1 : 0 });
    toast("Task done");
    reload();
  });
  view.querySelectorAll("[data-promo]").forEach((li) => li.onclick = async () => {
    const p = d.follow_ups.find((x) => x.id === +li.dataset.promo);
    if (await openForm("promos", p)) reload();
  });
  $("#restore").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!confirm("Restoring replaces ALL current data with the backup. Continue?")) return;
    try {
      await api("import", { method: "POST", body: JSON.parse(await file.text()) });
      toast("Backup restored");
      reload();
    } catch (err) { toast("Restore failed: " + err.message); }
  };
}

// ---------- Releases ----------
async function viewReleases() {
  const add = async () => {
    const r = await openForm("releases", {}, { status: "Planning", kind: "Single" });
    if (r && r.id) go(`#/release/${r.id}`);
  };
  shell("Releases", { add });
  const rows = await list("releases");
  view.innerHTML = rows.length ? `<div class="card"><ul class="list">${rows.map((r) => `
    <li class="row-link" data-go="#/release/${r.id}"><div class="grow">
      <div><b>${esc(r.title)}</b></div>
      <div class="sub">${esc(r.kind)}${r.artist ? " · " + esc(r.artist) : ""}${r.release_date ? " · " + fmtDate(r.release_date) : ""}</div>
    </div><span class="chip ${statusCls(r.status)}">${esc(r.status)}</span></li>`).join("")}</ul></div>`
    : `<div class="card empty">No releases yet.<br><br><button class="btn primary" id="first">+ New release</button>
       <p class="muted">A release comes with a ready-made checklist (mix, master, splits, PRO, distributor, pitching, release day) dated from your release date.</p></div>`;
  $("#first")?.addEventListener("click", add);
}

async function viewRelease(id) {
  const [r, tasks, songs, promos] = await Promise.all([
    get("releases", id), list("checklist", { release_id: id }),
    list("songs", { release_id: id }), list("promos", { release_id: id })]);
  shell(r.title, { back: true, add: async () => {
    if (await openForm("checklist", {}, { release_id: id, sort: tasks.length + 100 })) reload();
  }});
  const doneN = tasks.filter((t) => t.done).length;
  const showDone = sessionStorage.getItem("showDone") === "1";
  const visible = showDone ? tasks : tasks.filter((t) => !t.done);
  view.innerHTML = `
    <div class="card">
      <dl class="kv">
        <dt>Type</dt><dd>${esc(r.kind)}</dd>
        <dt>Status</dt><dd><span class="chip ${statusCls(r.status)}">${esc(r.status)}</span></dd>
        <dt>Release</dt><dd>${r.release_date ? fmtDate(r.release_date) + " " + dueChip(r.release_date, r.status === "Released") : '<span class="muted">no date yet</span>'}</dd>
        ${r.artist ? `<dt>Artist</dt><dd>${esc(r.artist)}</dd>` : ""}
        ${r.distributor ? `<dt>Distributor</dt><dd>${esc(r.distributor)}</dd>` : ""}
        ${r.upc ? `<dt>UPC</dt><dd>${esc(r.upc)}</dd>` : ""}
        ${r.notes ? `<dt>Notes</dt><dd>${esc(r.notes)}</dd>` : ""}
      </dl>
      <button class="btn small" id="edit">Edit release</button>
    </div>
    <div class="card"><h2>Checklist · ${doneN}/${tasks.length}</h2>
      <div class="bar"><i style="width:${tasks.length ? 100 * doneN / tasks.length : 0}%"></i></div>
      <ul class="list">${visible.map((t) => `
        <li class="${t.done ? "done" : ""}"><input type="checkbox" data-task="${t.id}" ${t.done ? "checked" : ""}>
        <div class="grow row-link" data-edit-task="${t.id}"><div>${esc(t.task)}</div>
        ${t.due_date ? `<div class="sub">${fmtDate(t.due_date)}</div>` : ""}</div>
        ${dueChip(t.due_date, t.done)}</li>`).join("") || '<li class="empty">All tasks done 🎉</li>'}</ul>
      <button class="btn small" id="toggleDone">${showDone ? "Hide" : "Show"} completed</button>
      <button class="btn small" id="addTask">+ Task</button>
    </div>
    <div class="card"><h2>Songs & splits</h2>
      <ul class="list">${songs.map((s) => `<li class="row-link" data-go="#/song/${s.id}"><div class="grow">${esc(s.title)}
        ${s.isrc ? `<div class="sub">ISRC ${esc(s.isrc)}</div>` : ""}</div><span class="muted">›</span></li>`).join("")
        || '<li class="empty">No songs linked yet.</li>'}</ul>
      <button class="btn small" id="addSong">+ Song</button>
    </div>
    <div class="card"><h2>Promo</h2>
      <ul class="list">${promos.map((p) => `<li class="row-link" data-promo="${p.id}"><div class="grow">${esc(p.outlet)}
        <div class="sub">${esc(p.kind)}</div></div><span class="chip ${statusCls(p.status)}">${esc(p.status)}</span></li>`).join("")
        || '<li class="empty">No promo tracked yet.</li>'}</ul>
      <button class="btn small" id="addPromo">+ Promo target</button>
    </div>`;

  $("#edit").onclick = async () => {
    const res = await openForm("releases", r);
    if (res === "deleted") go("#/releases"); else if (res) reload();
  };
  view.querySelectorAll("[data-task]").forEach((cb) => cb.onchange = async () => {
    await update("checklist", cb.dataset.task, { done: cb.checked ? 1 : 0 });
    reload();
  });
  view.querySelectorAll("[data-edit-task]").forEach((el) => el.onclick = async () => {
    if (await openForm("checklist", tasks.find((t) => t.id === +el.dataset.editTask))) reload();
  });
  $("#toggleDone").onclick = () => { sessionStorage.setItem("showDone", showDone ? "0" : "1"); reload(); };
  $("#addTask").onclick = () => addAction();
  $("#addSong").onclick = async () => {
    const s = await openForm("songs", {}, { release_id: id });
    if (s && s.id) go(`#/song/${s.id}`);
  };
  $("#addPromo").onclick = async () => {
    if (await openForm("promos", {}, { release_id: id, status: "To pitch", kind: "Playlist" })) reload();
  };
  view.querySelectorAll("[data-promo]").forEach((li) => li.onclick = async () => {
    if (await openForm("promos", promos.find((p) => p.id === +li.dataset.promo))) reload();
  });
}

// ---------- Songs / split sheets ----------
async function viewSongs() {
  const add = async () => {
    const s = await openForm("songs");
    if (s && s.id) go(`#/song/${s.id}`);
  };
  shell("Split sheets", { add });
  const [songs, splits, releases] = await Promise.all([list("songs"), list("splits"), list("releases")]);
  const relName = Object.fromEntries(releases.map((r) => [r.id, r.title]));
  view.innerHTML = songs.length ? `<div class="card"><ul class="list">${songs.map((s) => {
    const rows = splits.filter((x) => x.song_id === s.id);
    const total = rows.reduce((a, x) => a + (+x.writer_pct || 0), 0);
    const signed = rows.filter((x) => x.signed).length;
    const ok = rows.length && Math.abs(total - 100) < 0.01;
    return `<li class="row-link" data-go="#/song/${s.id}"><div class="grow"><div><b>${esc(s.title)}</b></div>
      <div class="sub">${rows.length} writer${rows.length === 1 ? "" : "s"} · ${signed}/${rows.length} signed${s.release_id && relName[s.release_id] ? " · " + esc(relName[s.release_id]) : ""}</div></div>
      <span class="chip ${ok ? (signed === rows.length ? "ok" : "warn") : "bad"}">${pct(total)}</span></li>`;
  }).join("")}</ul></div>`
    : `<div class="card empty">No songs yet.<br><br><button class="btn primary" id="first">+ New split sheet</button>
       <p class="muted">Write down who wrote what the day you write it. Future you will thank you.</p></div>`;
  $("#first")?.addEventListener("click", add);
}

async function viewSong(id) {
  const [s, rows] = await Promise.all([get("songs", id), list("splits", { song_id: id })]);
  const addSplit = async () => {
    if (await openForm("splits", {}, { song_id: id, role: "Songwriter" })) reload();
  };
  shell(s.title, { back: true, add: addSplit });
  const sum = (k) => rows.reduce((a, x) => a + (+x[k] || 0), 0);
  const tw = sum("writer_pct"), tp = sum("pub_pct"), tm = sum("master_pct");
  const flag = (t) => rows.length && Math.abs(t - 100) > 0.01 && t !== 0 ? "bad" : "";
  view.innerHTML = `
    <div class="card"><h2>Writers & shares</h2>
      ${rows.length ? `<ul class="list">${rows.map((x) => `
        <li class="row-link" data-split="${x.id}"><div class="grow"><div><b>${esc(x.name)}</b> ${x.signed ? '<span class="chip ok">signed</span>' : '<span class="chip warn">unsigned</span>'}</div>
          <div class="sub">${esc(x.role)}${x.pro ? " · " + esc(x.pro) : ""}${x.ipi ? " · IPI " + esc(x.ipi) : ""}${x.publisher ? " · " + esc(x.publisher) : ""}</div></div>
          <div class="pct">${pct(x.writer_pct)}<div class="sub">pub ${pct(x.pub_pct)} · master ${pct(x.master_pct)}</div></div></li>`).join("")}
        <li class="total"><div class="grow">Total</div><div class="pct">
          <span class="chip ${flag(tw) || "ok"}">writer ${pct(tw)}</span>
          <div class="sub"><span class="${flag(tp) && "overdue"}">pub ${pct(tp)}</span> · <span class="${flag(tm) && "overdue"}">master ${pct(tm)}</span></div></div></li>
      </ul>` : '<p class="empty">No writers yet. Tap + to add one.</p>'}
      ${rows.length && Math.abs(tw - 100) > 0.01 ? `<p class="overdue">Writer shares must total 100% (now ${pct(tw)}).</p>` : ""}
      <button class="btn small primary" id="addSplit">+ Writer</button>
      ${rows.length > 1 ? '<button class="btn small" id="even">Split writer % evenly</button>' : ""}
      ${rows.length ? `<a class="btn small" href="/splitsheet/${id}" target="_blank">Printable split sheet</a>
        <button class="btn small" id="share">Share as text</button>` : ""}
    </div>
    <div class="card"><h2>Song info</h2>
      <dl class="kv">
        ${s.isrc ? `<dt>ISRC</dt><dd>${esc(s.isrc)}</dd>` : ""}
        ${s.date_written ? `<dt>Written</dt><dd>${fmtDate(s.date_written)}</dd>` : ""}
        ${s.studio ? `<dt>Where</dt><dd>${esc(s.studio)}</dd>` : ""}
        ${s.release_id ? `<dt>Release</dt><dd><a href="#/release/${s.release_id}">open release</a></dd>` : ""}
        ${s.notes ? `<dt>Notes</dt><dd>${esc(s.notes)}</dd>` : ""}
      </dl>
      <button class="btn small" id="edit">Edit song</button>
    </div>`;

  $("#addSplit").onclick = addSplit;
  $("#edit").onclick = async () => {
    const res = await openForm("songs", s);
    if (res === "deleted") go("#/songs"); else if (res) reload();
  };
  view.querySelectorAll("[data-split]").forEach((li) => li.onclick = async () => {
    if (await openForm("splits", rows.find((x) => x.id === +li.dataset.split))) reload();
  });
  $("#even")?.addEventListener("click", async () => {
    if (!confirm(`Give each of the ${rows.length} writers an equal writer share?`)) return;
    // Spread rounding remainder onto the first writer so it totals exactly 100.
    const each = Math.floor(10000 / rows.length) / 100;
    const first = Math.round((100 - each * (rows.length - 1)) * 100) / 100;
    await Promise.all(rows.map((x, i) => update("splits", x.id, { writer_pct: i ? each : first })));
    reload();
  });
  $("#share")?.addEventListener("click", async () => {
    const text = `SPLIT SHEET: ${s.title}${s.isrc ? " (ISRC " + s.isrc + ")" : ""}\n` +
      rows.map((x) => `- ${x.name} (${x.role || "writer"}${x.pro ? ", " + x.pro : ""}${x.ipi ? ", IPI " + x.ipi : ""}): writer ${pct(x.writer_pct)}, publishing ${pct(x.pub_pct)}${x.publisher ? " via " + x.publisher : ""}, master ${pct(x.master_pct)}`).join("\n") +
      `\nTotal writer share: ${pct(tw)}`;
    try {
      if (navigator.share) await navigator.share({ title: `Split sheet: ${s.title}`, text });
      else { await navigator.clipboard.writeText(text); toast("Copied to clipboard"); }
    } catch { prompt("Copy this split sheet:", text); }
  });
}

// ---------- People ----------
async function viewPeople() {
  const add = async () => {
    const c = await openForm("collaborators", {}, { role: "Producer" });
    if (c && c.id) go(`#/person/${c.id}`);
  };
  shell("Collaborators", { add });
  const rows = await list("collaborators");
  const q = sessionStorage.getItem("peopleQ") || "";
  view.innerHTML = `<input class="search" id="q" type="search" placeholder="Search name, role, notes…" value="${esc(q)}">
    <div class="card"><ul class="list" id="plist"></ul></div>`;
  const draw = () => {
    const term = $("#q").value.toLowerCase();
    sessionStorage.setItem("peopleQ", term);
    const hits = rows.filter((c) => !term ||
      [c.name, c.role, c.notes, c.email, c.publisher].join(" ").toLowerCase().includes(term));
    $("#plist").innerHTML = hits.map((c) => `
      <li class="row-link" data-go="#/person/${c.id}"><div class="grow"><div><b>${esc(c.name)}</b></div>
      <div class="sub">${esc(c.role)}${c.pro ? " · " + esc(c.pro) : ""}</div></div>
      ${c.phone ? `<a class="btn small" href="tel:${esc(c.phone)}">Call</a>` : ""}
      ${c.email ? `<a class="btn small" href="mailto:${esc(c.email)}">Email</a>` : ""}</li>`).join("")
      || `<li class="empty">${rows.length ? "No matches." : "No collaborators yet. Tap + to add producers, co-writers, engineers…"}</li>`;
  };
  $("#q").oninput = draw;
  draw();
}

async function viewPerson(id) {
  const [c, log, splits, songs] = await Promise.all([
    get("collaborators", id), list("contact_log", { collaborator_id: id }),
    list("splits", { collaborator_id: id }), list("songs")]);
  const addLog = async () => {
    if (await openForm("contact_log", {}, { collaborator_id: id, date: today(), method: "Text" })) reload();
  };
  shell(c.name, { back: true, add: addLog });
  const songName = Object.fromEntries(songs.map((s) => [s.id, s.title]));
  view.innerHTML = `
    <div class="card">
      <dl class="kv">
        ${c.role ? `<dt>Role</dt><dd>${esc(c.role)}</dd>` : ""}
        ${c.phone ? `<dt>Phone</dt><dd><a href="tel:${esc(c.phone)}">${esc(c.phone)}</a> · <a href="sms:${esc(c.phone)}">text</a></dd>` : ""}
        ${c.email ? `<dt>Email</dt><dd><a href="mailto:${esc(c.email)}">${esc(c.email)}</a></dd>` : ""}
        ${c.pro ? `<dt>PRO</dt><dd>${esc(c.pro)}</dd>` : ""}
        ${c.ipi ? `<dt>IPI/CAE</dt><dd>${esc(c.ipi)}</dd>` : ""}
        ${c.publisher ? `<dt>Publisher</dt><dd>${esc(c.publisher)}</dd>` : ""}
        ${c.socials ? `<dt>Socials</dt><dd>${esc(c.socials)}</dd>` : ""}
        ${c.notes ? `<dt>Notes</dt><dd>${esc(c.notes)}</dd>` : ""}
      </dl>
      <button class="btn small" id="edit">Edit</button>
    </div>
    <div class="card"><h2>Contact log</h2>
      <ul class="list">${log.map((l) => `<li class="row-link" data-log="${l.id}"><div class="grow">
        <div>${esc(l.note) || '<span class="muted">(no note)</span>'}</div>
        <div class="sub">${fmtDate(l.date)} · ${esc(l.method)}</div></div></li>`).join("")
        || '<li class="empty">No contact logged yet.</li>'}</ul>
      <button class="btn small primary" id="addLog">+ Log contact</button>
    </div>
    <div class="card"><h2>On split sheets</h2>
      <ul class="list">${splits.map((x) => `<li class="row-link" data-go="#/song/${x.song_id}"><div class="grow">${esc(songName[x.song_id] || "Song")}
        <div class="sub">${esc(x.role)}</div></div><span class="pct">${pct(x.writer_pct)}</span></li>`).join("")
        || '<li class="empty">Not on any split sheet yet.</li>'}</ul>
    </div>`;
  $("#edit").onclick = async () => {
    const res = await openForm("collaborators", c);
    if (res === "deleted") go("#/people"); else if (res) reload();
  };
  $("#addLog").onclick = addLog;
  view.querySelectorAll("[data-log]").forEach((li) => li.onclick = async () => {
    if (await openForm("contact_log", log.find((l) => l.id === +li.dataset.log))) reload();
  });
}

// ---------- Promo ----------
async function viewPromo() {
  const add = async () => {
    if (await openForm("promos", {}, { status: "To pitch", kind: "Playlist", pitched_on: "" })) reload();
  };
  shell("Promo tracker", { add });
  const [rows, releases] = await Promise.all([list("promos"), list("releases")]);
  const relName = Object.fromEntries(releases.map((r) => [r.id, r.title]));
  const fStatus = sessionStorage.getItem("promoStatus") || "";
  const fRel = sessionStorage.getItem("promoRel") || "";
  const counts = (s) => rows.filter((r) => r.status === s).length;
  const won = rows.filter((r) => ["Accepted", "Published"].includes(r.status)).length;
  const pitched = rows.filter((r) => r.status !== "To pitch").length;
  const spent = rows.reduce((a, r) => a + (+r.cost || 0), 0);
  view.innerHTML = `
    <div class="stats">
      <div class="stat"><b>${pitched}</b><small>pitched</small></div>
      <div class="stat"><b>${won}</b><small>wins${pitched ? ` (${Math.round(100 * won / pitched)}%)` : ""}</small></div>
      <div class="stat"><b>$${spent.toFixed(0)}</b><small>spent</small></div>
    </div>
    <div class="filters">
      <select id="fs"><option value="">All statuses</option>${OPT.promoStatus.map((s) =>
        `<option ${s === fStatus ? "selected" : ""}>${s}</option>`).join("")}</select>
      <select id="fr"><option value="">All releases</option>${releases.map((r) =>
        `<option value="${r.id}" ${String(r.id) === fRel ? "selected" : ""}>${esc(r.title)}</option>`).join("")}</select>
    </div>
    <div class="card"><ul class="list">${rows.filter((r) =>
      (!fStatus || r.status === fStatus) && (!fRel || String(r.release_id) === fRel)).map((p) => `
      <li class="row-link" data-promo="${p.id}"><div class="grow"><div><b>${esc(p.outlet)}</b></div>
        <div class="sub">${esc(p.kind)}${p.contact ? " · " + esc(p.contact) : ""}${p.release_id && relName[p.release_id] ? " · " + esc(relName[p.release_id]) : ""}</div>
        ${p.result_link ? `<a class="sub" href="${esc(p.result_link)}" target="_blank" rel="noopener">result link</a>` : ""}</div>
        <div style="text-align:right"><span class="chip ${statusCls(p.status)}">${esc(p.status)}</span>
        <div>${["To pitch", "Pitched", "Followed up"].includes(p.status) ? dueChip(p.follow_up) : ""}</div>
        ${nextStatus(p.status) ? `<button class="btn small" data-next="${p.id}">→ ${nextStatus(p.status)}</button>` : ""}</div></li>`).join("")
      || `<li class="empty">${rows.length ? "Nothing matches the filter." : "Track every playlist, blog and station you pitch. Tap + to add one."}</li>`}</ul></div>
    <p class="muted">${OPT.promoStatus.map((s) => `${s}: ${counts(s)}`).join(" · ")}</p>`;

  $("#fs").onchange = (e) => { sessionStorage.setItem("promoStatus", e.target.value); reload(); };
  $("#fr").onchange = (e) => { sessionStorage.setItem("promoRel", e.target.value); reload(); };
  view.querySelectorAll("[data-promo]").forEach((li) => li.onclick = async (e) => {
    if (e.target.closest("button,a")) return;
    if (await openForm("promos", rows.find((p) => p.id === +li.dataset.promo))) reload();
  });
  view.querySelectorAll("[data-next]").forEach((b) => b.onclick = async () => {
    const p = rows.find((x) => x.id === +b.dataset.next);
    const status = nextStatus(p.status);
    const patch = { status };
    // Pitching starts a one-week follow-up clock.
    if (status === "Pitched") {
      patch.pitched_on = p.pitched_on || today();
      patch.follow_up = shiftDate(today(), 7);
    } else if (status === "Followed up") {
      patch.follow_up = shiftDate(today(), 7);
    }
    await update("promos", p.id, patch);
    toast(`${p.outlet}: ${status}`);
    reload();
  });
}
const nextStatus = (s) => ({ "To pitch": "Pitched", Pitched: "Followed up" }[s]);
function shiftDate(d, n) {
  const dt = new Date(d + "T00:00:00");
  dt.setDate(dt.getDate() + n);
  return dt.toLocaleDateString("en-CA");
}

render();

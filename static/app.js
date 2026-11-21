// Throughline front end. Plain JavaScript, no framework.
// One long page. Each section has a render function; refreshAll() redraws them after any change.
const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (url, opts) => {
  const r = await fetch(url, opts && { headers: { "Content-Type": "application/json" }, ...opts, body: opts.body && JSON.stringify(opts.body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || "Something went wrong");
  return j;
};
const state = { meeting: null, status: { art: {} } };
const COLORS = ["#ffd96b", "#9fd0ff", "#9be8c4", "#ffb79c", "#cdb8ff", "#ffb3c9"];
const hash = (n) => [...n].reduce((a, c) => a + c.charCodeAt(0), 0);
const todayStr = () => $("#today").value;
const fmt = (d) => d ? new Date(d + "T00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "No deadline";
const go = (id) => document.getElementById(id).scrollIntoView({ behavior: "smooth", block: "start" });
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 3200); }

// avatar: 3D picture if the user added avatars (static/av1.png ...), otherwise a coloured initial
function avatar(name, cls = "") {
  const imgs = state.status.art.av || [];
  if (imgs.length) return `<div class="av ${cls}" style="background:#e7eefc"><img src="${imgs[hash(name) % imgs.length]}" alt=""></div>`;
  return `<div class="av ${cls}" style="background:${COLORS[hash(name) % COLORS.length]}">${esc(name[0] || "?")}</div>`;
}
const ICONS = {
  "launch date": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0b57e3" stroke-width="2.4" stroke-linecap="round"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>',
  database: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0b57e3" stroke-width="2.4"><ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></svg>',
  budget: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0b57e3" stroke-width="2.4" stroke-linecap="round"><rect x="3" y="6" width="18" height="14" rx="3"/><path d="M3 10h18M16 15h2"/></svg>',
  platform: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0b57e3" stroke-width="2.4" stroke-linecap="round"><rect x="7" y="2" width="10" height="20" rx="3"/><path d="M11 18h2"/></svg>',
  general: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0b57e3" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>',
};
const PINCOLORS = { "launch date": "#0b57e3", database: "#ff6b3d", budget: "#12a36e", platform: "#8a5cf6", general: "#0b57e3" };
function pin(topic, old) {
  const imgs = state.status.art.pin || [];
  const keys = Object.keys(PINCOLORS);
  const k = keys.includes(topic) ? keys.indexOf(topic) : hash(topic) % keys.length;
  const inner = imgs.length
    ? `<img src="${imgs[k % imgs.length]}" alt="">`
    : `<div class="pin" style="border-color:${old ? "#aab2c4" : PINCOLORS[topic] || "#0b57e3"}"><span>${ICONS[topic] || ICONS.general}</span></div>`;
  return `<div class="pinwrap ${old ? "old" : ""}">${inner}<div class="base"></div></div>`;
}

// ---------- scroll reveal + nav
const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && e.target.classList.add("in")), { threshold: 0.08 });
document.querySelectorAll(".rv").forEach((el) => io.observe(el));

// ---------- hero + stats
$("#btnDemo").onclick = async () => {
  const mem = await api("/api/memory");
  await api("/api/demo", { method: "POST", body: {} });
  toast("Demo memory loaded: last week's kickoff is now remembered.");
  await fillSample(2); await refreshAll(); go("capture");
};
async function renderStats() {
  const mem = await api("/api/memory"); const board = await api("/api/board"); const ms = await api("/api/meetings");
  $("#stDec").textContent = mem.filter((d) => d.status === "active").length;
  $("#stRev").textContent = mem.filter((d) => d.status === "superseded").length;
  $("#stMeet").textContent = ms.filter((m) => m.status === "committed").length;
  $("#stTask").textContent = board.filter((a) => a.status === "posted").length;
}

// ---------- capture
async function fillSample(n) {
  const s = await api("/api/sample"); const m = n === 1 ? s.meeting1 : s.meeting2;
  $("#mTitle").value = m.title; $("#mDate").value = m.date; $("#mText").value = m.transcript; liveParse();
}
$("#btnS1").onclick = () => fillSample(1);
$("#btnS2").onclick = () => fillSample(2);
$("#mFile").onchange = async (e) => {
  const f = e.target.files[0]; if (!f) return;
  let t = await f.text();
  t = t.split("\n").filter((l) => !/^(WEBVTT|\d+\s*$|[\d:.,]+\s*-->)/.test(l.trim())).join("\n").replace(/<v ([^>]+)>/g, "$1: ").replace(/<\/?v>/g, "");
  $("#mText").value = t; $("#mTitle").value = f.name.replace(/\.\w+$/, ""); liveParse();
};
function liveParse() {
  const re = /^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?([A-Za-z][\w .'-]{0,30}):\s*(.+)$/;
  const names = {}; let lines = 0;
  $("#mText").value.split("\n").forEach((l) => { const m = l.match(re); if (m) { lines++; names[m[1].trim()] = 1; } });
  const list = Object.keys(names);
  $("#spN").textContent = list.length; $("#lnN").textContent = lines;
  const spots = [[12, 10], [58, 4], [34, 38], [68, 44], [8, 56], [44, 68], [76, 74]];
  $("#who").innerHTML = list.slice(0, 7).map((n, i) => `<div class="bub" style="left:${spots[i][0]}%;top:${spots[i][1]}%;animation-delay:-${i * 0.9}s">${avatar(n)}<small>${esc(n)}</small></div>`).join("");
}
$("#mText").oninput = liveParse;
$("#btnRun").onclick = async () => {
  $("#capErr").textContent = ""; const btn = $("#btnRun"); btn.disabled = true; btn.textContent = "Analyzing…";
  try {
    state.meeting = await api("/api/meetings", { method: "POST", body: { title: $("#mTitle").value, date: $("#mDate").value, transcript: $("#mText").value } });
    renderReview(); go("review");
  } catch (e) { $("#capErr").textContent = e.message; }
  btn.disabled = false; btn.textContent = "Analyze meeting →";
};

// ---------- review (the confirmation gate lives here)
async function refreshMeeting() { state.meeting = await api("/api/meetings/" + state.meeting.id); }
const FLAG = { no_owner: ["orange", "No owner: pick one"], unknown_owner: ["amber", "Owner not in this meeting"], no_deadline: ["amber", "No deadline"], check_date: ["amber", "Check the date"] };
function flagBadge(f, aid) {
  if (f.startsWith("duplicate:")) { const n = f.split(":")[1]; return `<span class="tag blue">Similar to TL-${n}: revised or repeated?</span><button class="pill ghost sm" data-merge="${n}" data-aid="${aid}">Update TL-${n} instead</button>`; }
  const [c, t] = FLAG[f] || ["", f]; return `<span class="tag ${c}">${t}</span>`;
}
const head = (title, sub) => `<div class="sec-head"><svg class="ticks" width="40" height="34" viewBox="0 0 46 40"><path d="M8 30 L2 14 M20 22 L18 4" stroke="#0b57e3" stroke-width="3" stroke-linecap="round" fill="none"/></svg><h2>${title}</h2>${sub ? `<p class="lead">${sub}</p>` : ""}</div>`;
function renderReview() {
  const el = $("#reviewScene"); const m = state.meeting;
  if (!m) { el.innerHTML = head("Review before anything happens", "Conflicts, decisions and tasks show up here after you analyze a meeting.") + `<div class="empty">Nothing to review yet.<br><br><a class="pill dark" href="#capture">Go to Capture</a></div>`; return; }
  if (m.status !== "review") { el.innerHTML = head(`${esc(m.title)} is ${m.status}`, "This meeting is closed. See Memory and Board for the result.") + `<div class="row"><a class="pill dark" href="#memory">Open Memory</a><a class="pill ghost" href="#capture">Analyze another</a></div>`; return; }
  const unresolved = m.conflicts.filter((c) => !c.resolution).length;
  const approved = m.actions.filter((a) => a.approved).length;
  el.innerHTML = head(`Review: <span class="scribble">${esc(m.title)}<svg viewBox="0 0 300 18" preserveAspectRatio="none"><path d="M3 12 C60 4 120 16 180 8 S270 6 297 10" stroke="#ff6b3d" stroke-width="5" fill="none" stroke-linecap="round" style="stroke-dashoffset:0"/></svg></span>`,
    `<span class="tag ${m.mode === "ai" ? "green" : "amber"}">${m.mode === "ai" ? "AI extraction" : "Fallback rules"}</span> ${esc(m.note)}. Speakers: ${m.speakers.map(esc).join(", ")}. Nothing is saved or posted until you confirm.`) + `
    <div class="subhead"><h3>Conflicts with earlier meetings</h3><span class="tag ${unresolved ? "orange" : "green"}">${m.conflicts.length ? unresolved + " to resolve" : "none found"}</span></div>
    ${m.conflicts.map(conflictCard).join("") || `<div class="empty">No contradictions with memory.</div>`}
    <div class="subhead"><h3>Decisions</h3><span class="tag grey">${m.decisions.length}</span></div>
    <div class="decs">${m.decisions.map((d) => `<div class="dec"><small>${esc(d.topic)} · ${esc(d.speaker)}</small>${esc(d.text)}</div>`).join("") || '<div class="empty">No decisions found.</div>'}</div>
    <div class="subhead"><h3>Action items</h3><span class="tag grey">${approved} of ${m.actions.length} ticked</span></div>
    <div class="tasks">${m.actions.map(actionRow).join("") || '<div class="empty">No action items found.</div>'}</div>
    <div class="confirmbar"><span>${unresolved ? unresolved + " conflict(s) still need your call" : approved + " task(s) will be posted after you confirm"}</span>
      <div class="row"><button class="pill danger sm" id="btnDiscard">Discard meeting</button><button class="pill dark" id="btnReview" ${unresolved ? "disabled" : ""}>Review &amp; confirm →</button></div></div>`;
  el.querySelectorAll("[data-res]").forEach((b) => b.onclick = async () => {
    await api(`/api/conflicts/${b.dataset.cid}/resolve`, { method: "POST", body: { resolution: b.dataset.res } });
    await refreshMeeting(); renderReview();
  });
  el.querySelectorAll("[data-chk]").forEach((b) => b.onclick = () => patchAction(+b.dataset.chk, { approved: b.classList.contains("on") ? 0 : 1 }));
  el.querySelectorAll("[data-f]").forEach((i) => i.onchange = () => patchAction(+i.dataset.id, { [i.dataset.f]: i.value }));
  el.querySelectorAll("[data-merge]").forEach((b) => b.onclick = async () => {
    await api(`/api/actions/${b.dataset.aid}/merge`, { method: "POST", body: { into: +b.dataset.merge } });
    toast(`Updated TL-${b.dataset.merge} with the new owner and deadline.`); await refreshMeeting(); renderReview();
  });
  $("#btnReview").onclick = openConfirm;
  $("#btnDiscard").onclick = async () => { if (confirm("Discard this meeting? Nothing will be saved.")) { await api(`/api/meetings/${m.id}/discard`, { method: "POST", body: {} }); await refreshMeeting(); renderReview(); } };
}
function conflictCard(c) {
  const d = c.resolution;
  return `<div class="conf ${d ? "resolved" : ""}">
    <div class="old"><span class="tag grey">${esc(c.old_meeting)} · ${fmt(c.old_date)}</span><p class="t">${esc(c.old_text)}</p></div>
    <div class="mid"><span class="vs">vs</span></div>
    <div><span class="tag blue">This meeting</span><p class="t">${esc(c.new_text)}</p></div>
    <div class="why">${esc(c.explanation)}</div>
    <div class="acts"><button class="pill sm ${d === "replace" ? "blue" : "ghost"}" data-cid="${c.id}" data-res="replace">Replace the old decision</button>
      <button class="pill sm ${d === "keep_old" ? "blue" : "ghost"}" data-cid="${c.id}" data-res="keep_old">Keep the old decision</button>
      ${d ? '<span class="tag green">Resolved</span>' : '<span class="tag orange">Needs your call</span>'}</div></div>`;
}
function actionRow(a) {
  const on = a.approved ? "on" : "";
  return `<div class="trow"><div class="check ${on}" data-chk="${a.id}">${on ? "✓" : ""}</div>
    <div><input data-id="${a.id}" data-f="task" value="${esc(a.task)}"><div class="flags">${a.flags.map((f) => flagBadge(f, a.id)).join("")}</div><div class="q">"${esc(a.quote)}"</div></div>
    <input data-id="${a.id}" data-f="owner" value="${esc(a.owner)}" aria-label="Owner">
    <input type="date" data-id="${a.id}" data-f="deadline" value="${a.deadline || ""}" aria-label="Deadline"></div>`;
}
async function patchAction(id, body) {
  try { await api("/api/actions/" + id, { method: "PATCH", body }); } catch (e) { toast(e.message); }
  await refreshMeeting(); renderReview();
}
function openConfirm() {
  const m = state.meeting; const yes = m.actions.filter((a) => a.approved); const no = m.actions.filter((a) => !a.approved);
  const keepOld = m.conflicts.filter((c) => c.resolution === "keep_old").map((c) => c.new_text);
  const repl = m.conflicts.filter((c) => c.resolution === "replace");
  $("#sheet").innerHTML = `<span class="tag blue">Confirm before posting</span><h3>This is exactly what will happen</h3>
    <span class="tag green">${yes.length} task(s) posted to the tracker${state.status.github ? " and GitHub Issues" : ""}</span>
    <ul>${yes.map((a) => `<li><b>${esc(a.owner)}</b>: ${esc(a.task)} <small>${fmt(a.deadline)}</small></li>`).join("") || "<li>No tasks selected</li>"}</ul>
    <span class="tag orange">${no.length} task(s) will NOT be sent</span>
    <ul>${no.map((a) => `<li>${esc(a.task)}</li>`).join("") || "<li>None</li>"}</ul>
    <span class="tag grey">Memory</span><ul>
      <li>${m.decisions.length - keepOld.length} decision(s) become active</li>
      ${repl.map((c) => `<li>Replaces: <s>${esc(c.old_text)}</s></li>`).join("")}
      ${keepOld.map((t) => `<li>Dropped (old one kept): ${esc(t)}</li>`).join("")}</ul>
    <div class="row"><button class="pill ghost" id="cNo">Go back</button><button class="pill dark" id="cYes">Confirm &amp; post</button></div>`;
  $("#modal").classList.add("open");
  $("#cNo").onclick = () => $("#modal").classList.remove("open");
  $("#cYes").onclick = async () => {
    try {
      const r = await api(`/api/meetings/${m.id}/commit`, { method: "POST", body: { confirm: true } });
      $("#modal").classList.remove("open"); await refreshMeeting(); await refreshAll();
      toast(`Posted ${r.posted.length} task(s). Memory updated.`); go("board");
    } catch (e) { toast(e.message); $("#modal").classList.remove("open"); }
  };
}
$("#modal").onclick = (e) => { if (e.target.id === "modal") $("#modal").classList.remove("open"); };

// ---------- memory (pins on a dotted map)
async function renderMemory() {
  const ds = await api("/api/memory");
  if (!ds.length) { $("#memBody").innerHTML = `<div class="empty">Memory is empty. Confirm a meeting, or press <b>Load demo</b> at the top.</div>`; return; }
  const byTopic = {}; ds.forEach((d) => (byTopic[d.topic] = byTopic[d.topic] || []).push(d));
  $("#memBody").innerHTML = Object.entries(byTopic).map(([t, list]) => `<div class="topic"><h3>${esc(t)}</h3><div class="path">${
    list.map((d, i) => `${i ? '<div class="dots"></div>' : ""}<div class="stop ${d.status === "superseded" ? "old" : ""}">${pin(t, d.status === "superseded")}
      <div class="card"><span class="tag ${d.status === "active" ? "green" : "grey"}">${d.status === "active" ? "current" : "replaced"}</span><p>${esc(d.text)}</p><small>${esc(d.meeting_title)} · ${fmt(d.meeting_date)} · ${esc(d.speaker)}</small></div></div>`).join("")}</div></div>`).join("");
}

// ---------- board + reminders
async function renderBoard() {
  const t = todayStr();
  const rem = await api("/api/reminders?today=" + t); const acts = await api("/api/board");
  $("#remBody").innerHTML = `<div class="subhead"><h3>Reminders</h3><span class="tag ${rem.length ? "orange" : "green"}">${rem.length}</span></div>` +
    (rem.length ? `<div class="rems">${rem.map((r) => `<div class="rem ${r.kind}"><div class="top">${avatar(r.owner)}<span class="tag ${r.kind === "overdue" ? "orange" : "amber"}">${r.kind}</span></div><p>${esc(r.message)}</p></div>`).join("")}</div>` : `<div class="empty">Nothing due in the next 2 days from ${fmt(t)}.</div>`);
  const open = acts.filter((a) => a.status === "posted"), done = acts.filter((a) => a.status === "done");
  const card = (a) => `<div class="task ${a.status}">${avatar(a.owner)}<div class="grow"><div class="tt">${esc(a.task)}</div><small>${esc(a.owner)} · ${fmt(a.deadline)} · ${esc(a.tracker_ref || "")}</small></div><div class="check ${a.status === "done" ? "on" : ""}" data-done="${a.id}" data-state="${a.status}">${a.status === "done" ? "✓" : ""}</div></div>`;
  $("#boardBody").innerHTML = `<div class="colcard"><h4>Open · ${open.length}</h4>${open.map(card).join("") || '<div class="empty">No open tasks.</div>'}</div>
    <div class="colcard"><h4>Done · ${done.length}</h4>${done.map(card).join("") || '<div class="empty">Nothing done yet.</div>'}</div>`;
  document.querySelectorAll("[data-done]").forEach((b) => b.onclick = async () => {
    await api(`/api/actions/${b.dataset.done}/done`, { method: "POST", body: { done: b.dataset.state !== "done" } }); refreshAll();
  });
}

// ---------- digest
async function renderDigest() {
  const people = await api("/api/digest?today=" + todayStr());
  const list = (arr) => arr.map((a) => `<li>${esc(a.task)} <small>· ${fmt(a.deadline)}</small></li>`).join("");
  $("#digBody").innerHTML = people.map((p) => `<div class="dcard"><div class="q">“</div><p class="nar">${esc(p.narrative)}</p>
    ${p.overdue.length ? `<span class="tag orange">Overdue</span><ul>${list(p.overdue)}</ul>` : ""}
    ${p.due_week.length ? `<span class="tag blue">Due this week</span><ul>${list(p.due_week)}</ul>` : ""}
    ${p.no_deadline.length ? `<span class="tag amber">Needs a deadline</span><ul>${list(p.no_deadline)}</ul>` : ""}
    <div class="who2">${avatar(p.person)}<div><b>${esc(p.person)}</b><small>${p.done.length} done · ${p.overdue.length + p.due_week.length + p.no_deadline.length} open</small></div></div></div>`).join("")
    || `<div class="empty" style="flex:1">No tasks on the board yet, so no digests.</div>`;
}
$("#dPrev").onclick = () => $("#digBody").scrollBy({ left: -380, behavior: "smooth" });
$("#dNext").onclick = () => $("#digBody").scrollBy({ left: 380, behavior: "smooth" });

// ---------- faq
const FAQ = [
  ["What if a decision is reversed later?", "Both versions stay in Memory. The old one turns grey and is linked to the new one, so you can see how the team changed its mind."],
  ["What if nobody owns a task?", "'Someone should...' becomes Unassigned. You cannot tick it until you type a name."],
  ["What if I say 'next Friday'?", "It picks a date, then shows a yellow Check the date tag, because that phrase has two readings."],
  ["What if the same task shows up twice?", "A task similar to an open one starts unticked, with a button to update the old task instead of creating a copy."],
  ["Can it post without me?", "No. The server refuses to post or save memory without your confirmation, and tasks you do not tick are never sent."],
  ["What is real and what is not?", "AI extraction, conflict judging and the digest text are real with your own Gemini key. Without it, simple rules run and the top chip says so. Reminders and the digest stay inside this app."],
];
$("#faqList").innerHTML = FAQ.map(([q, a]) => `<details><summary>${q}</summary><p>${a}</p></details>`).join("");

// ---------- start
async function refreshAll() { await Promise.all([renderStats(), renderMemory(), renderBoard(), renderDigest()]); renderReview(); }
$("#today").onchange = () => { renderBoard(); renderDigest(); };
(async function init() {
  state.status = await api("/api/status");
  $("#today").value = state.status.today; $("#mDate").value = state.status.today;
  const c = $("#aiChip");
  c.textContent = state.status.ai ? "AI live · " + state.status.model : "AI: fallback rules";
  c.classList.toggle("live", state.status.ai);
  const ic = state.status.art.bit || [];
  ["ic1", "ic2", "ic3"].forEach((id, i) => { $("#" + id).innerHTML = ic[[0, 2, 1][i]] ? `<img src="${ic[[0, 2, 1][i]]}" alt="">` : ["✎", "⌕", "✓"][i]; });
  const dm = $(".dotmap"), spots = [["launch date", 16, 38], ["database", 36, 20], ["platform", 58, 52], ["budget", 80, 30]];
  dm.innerHTML = spots.map(([t, x, y]) => `<div class="pinwrap" style="left:${x}%;top:${y}%;transform:scale(${t === "platform" ? 1.5 : 1})">${pin(t, false)}</div>`).join("");
  liveParse(); await refreshAll();
})();

// ---------- scroll motion (reveal stagger, parallax, progress bar)
const STAG = ".how-grid > *, .band > div, .conf, .stop, .topic, .task, .rem, .dcard, .faq-grid li, .faq-grid details, .cap-grid > *, .cols > *, .colcard, .dotmap .pinwrap, .bub, .fgrid > *";
function tagStagger() {
  document.querySelectorAll(".rv").forEach((sec) => {
    let i = 0;
    sec.querySelectorAll(STAG).forEach((el) => { if (!el.classList.contains("st") && !el.matches(".pinwrap,.bub")) el.classList.add("st"); el.style.setProperty("--i", i++ % 8); });
    sec.querySelectorAll(".pinwrap").forEach((el, k) => el.style.setProperty("--i", k % 6));
  });
}
new MutationObserver(() => tagStagger()).observe(document.body, { childList: true, subtree: true });
tagStagger();
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
let ticking = false;
function onScroll() {
  if (ticking) return; ticking = true;
  requestAnimationFrame(() => {
    const y = scrollY, max = document.documentElement.scrollHeight - innerHeight;
    $("#progress").style.transform = `scaleX(${max > 0 ? y / max : 0})`;
    if (!still && y < 1000) {
      const r = document.documentElement.style;
      r.setProperty("--py", `${y * -0.12}px`); r.setProperty("--py1", `${y * -0.22}px`);
      r.setProperty("--py2", `${y * 0.08}px`); r.setProperty("--pc", `${y * 0.06}px`);
    }
    ticking = false;
  });
}
addEventListener("scroll", onScroll, { passive: true }); onScroll();

/* Phenix-video — noyau de l'interface : état, API, notifications, routeur, panneau de résultat. */
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const enc = (p) => String(p).split("/").map(encodeURIComponent).join("/");
const mo = (n) => (n / 1048576).toFixed(1) + " Mo";
const fmtN = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + " M" : n >= 1e3 ? (n / 1e3).toFixed(1) + " k" : String(Math.round(n || 0)));

const S = { source: "", enhSrc: "", cur: null, timer: null, health: null, accounts: null, lastClips: "", lastProfile: "", page: "", jobs: [] };
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* stockage indisponible : sans importance */ } },
};

function toast(msg, type = "info", ms = 5200) {
  const t = document.createElement("div");
  t.className = "toast " + type;
  t.textContent = msg;
  $("toasts").appendChild(t);
  setTimeout(() => t.remove(), ms);
}

async function api(path, body, method) {
  const opt = body === undefined ? {} : { method: method || "POST", body: typeof body === "string" ? body : JSON.stringify(body) };
  let r;
  try { r = await fetch(path, opt); } catch (e) { throw new Error("Le serveur local ne répond pas."); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.error) throw new Error(j.error || "Erreur " + r.status);
  return j;
}
const safe = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { toast(e.message, "err"); } };

function upfile(input, cb) {
  const f = input.files[0];
  if (!f) return;
  const x = new XMLHttpRequest();
  x.open("POST", "/api/upload?name=" + encodeURIComponent(f.name));
  x.onload = () => { try { cb(JSON.parse(x.responseText).id, f); } catch (e) { toast("Échec de l'envoi du fichier.", "err"); } };
  x.onerror = () => toast("Échec de l'envoi du fichier.", "err");
  x.send(f);
}

/* ------------------------------------------------------------ routeur / menu */
const MENU = [
  { g: "Vue d'ensemble" },
  { id: "home", ic: "🏠", t: "Accueil", sub: "Tout ton studio en un coup d'œil" },
  { g: "Créer" },
  { id: "studio", ic: "🎬", t: "Studio clips & doublage", sub: "Découpe, sous-titres animés, traduction et voix off" },
  { id: "atelier", ic: "🛠️", t: "Atelier de montage", sub: "Améliorer, outils de montage, masquer ma marque" },
  { g: "Grandir" },
  { id: "trends", ic: "📈", t: "Tendances", sub: "Décortiquer des vidéos virales de ta niche" },
  { id: "insights", ic: "🎯", t: "Profil & niches", sub: "Analyse de profil, niche à viser, meilleurs horaires, planning" },
  { g: "Publier" },
  { id: "publish", ic: "🚀", t: "Publication", sub: "Dossier prêt à poster + envoi direct YouTube / TikTok" },
  { id: "accounts", ic: "🔗", t: "Comptes", sub: "Connexion YouTube et TikTok" },
  { g: "Système" },
  { id: "history", ic: "🗂️", t: "Historique", sub: "Tes derniers travaux" },
  { id: "settings", ic: "⚙️", t: "Réglages", sub: "Diagnostic, auto-test, thème" },
];
const PAGES = {}; // rempli par pages.js : { id: { render(el), init() } }

function buildNav() {
  $("nav").innerHTML = MENU.map((m) => m.g ? `<div class="grp">${esc(m.g)}</div>`
    : `<button class="nav-i" data-p="${m.id}"><span class="ic">${m.ic}</span>${esc(m.t)}<span class="badge hide" id="bd-${m.id}"></span></button>`).join("");
  document.querySelectorAll(".nav-i").forEach((b) => (b.onclick = () => go(b.dataset.p)));
}
function go(id, arg) {
  if (!PAGES[id] && id !== "job") id = "home";
  S.page = id;
  const m = MENU.find((x) => x.id === id) || { t: "Résultat", sub: "" };
  document.querySelectorAll(".nav-i").forEach((b) => b.classList.toggle("on", b.dataset.p === id));
  $("title").textContent = m.t;
  $("subtitle").textContent = m.sub || "";
  document.title = m.t + " · Phenix-video";
  document.body.classList.remove("nav-open");
  const el = $("main");
  el.innerHTML = "";
  PAGES[id].render(el, arg);
  PAGES[id].init && PAGES[id].init(el, arg);
  if (id !== "job") { S.cur = null; clearTimeout(S.timer); }
  try { history.replaceState(null, "", "#" + id); } catch (e) { /* ignoré */ }
  window.scrollTo(0, 0);
}

/* ------------------------------------------------------------ travaux */
async function startJob(kind, options, opt = {}) {
  const j = await api("/api/jobs", { kind, options });
  S.cur = j.id;
  const box = $("resbox");
  if (box) box.classList.remove("hide");
  poll();
  return j.id;
}
const runJob = safe(startJob);

function poll() {
  clearTimeout(S.timer);
  if (!S.cur) return;
  const id = S.cur;
  fetch("/api/jobs/" + id).then((r) => r.json()).then((v) => {
    if (id !== S.cur) return;
    if (v.error) { renderResult(null); return; }
    const live = v.status === "running" || v.status === "queued";
    if (live) S.seen = { ...(S.seen || {}), [v.id]: 1 };
    renderResult(v);
    if (live) S.timer = setTimeout(poll, 1500);
    else { afterJob(v); loadHistory(); }
  }).catch(() => { S.timer = setTimeout(poll, 3000); });
}
function setPill(id) {
  const p = $("runpill");
  if (!id) { p.classList.add("hide"); return; }
  p.className = "pill pulse";
  p.textContent = "Travail en cours";
  p.onclick = () => { S.cur = id; go("job", id); };
}
function afterJob(v) {
  if (!(S.seen && S.seen[v.id])) return;  // résultat simplement consulté : pas de notification
  if (v.status === "done") {
    if (v.kind === "clips") S.lastClips = v.id;
    if (v.kind === "insights_profile") S.lastProfile = v.id;
    if (!S.notified || S.notified !== v.id + v.status) {
      S.notified = v.id + v.status;
      toast({ clips: "Clips prêts.", publish: "Dossier de publication prêt.", youtube: "Envoyé sur YouTube.", tiktok: "Envoyé à TikTok.",
        yt_login: "YouTube connecté.", insights_profile: "Analyse terminée.", insights_niches: "Niches classées.", insights_plan: "Planning prêt." }[v.kind] || "Terminé.", "ok");
    }
    if (v.kind === "yt_login" || v.kind === "tiktok" || v.kind === "youtube") refreshAccounts();
  } else if (v.status === "error" && S.notified !== v.id + v.status) {
    S.notified = v.id + v.status;
    toast("Le travail a échoué : ouvre le journal pour le détail.", "err");
  }
}

const LABEL = { queued: "En attente", running: "En cours…", done: "Terminé", error: "Erreur", cancelled: "Annulé" };
const KIND = { clips: "Clips", delogo: "Masquage de marque", enhance: "Amélioration", publish: "Dossier de publication", trends: "Tendances", tool: "Outil de montage",
  doctor: "Diagnostic", selftest: "Auto-test", youtube: "Envoi YouTube", tiktok: "Envoi TikTok", yt_login: "Connexion YouTube",
  insights_profile: "Analyse de profil", insights_niches: "Recherche de niches", insights_plan: "Planning" };

function resultShell() {
  return `<section class="card hide" id="resbox"><h2>Résultat</h2><div id="status" class="note">Rien en cours.</div>
    <div class="btn-row hide" id="cancelrow" style="margin-top:8px"><button class="btn sm danger" id="cancel">Annuler</button></div>
    <div id="rich"></div><div class="vgrid" id="out"></div><div id="extra"></div>
    <details id="logd"><summary>Journal technique</summary><pre id="log"></pre></details></section>`;
}
function renderResult(v) {
  const box = $("resbox");
  if (!box) return;
  if (!v) { box.classList.add("hide"); return; }
  box.classList.remove("hide");
  const live = v.status === "running" || v.status === "queued";
  const errl = (v.log.split("\n").filter((x) => x.startsWith("[erreur]")).pop() || "");
  $("status").innerHTML = `<span class="st ${v.status}">${LABEL[v.status] || v.status}</span> ${esc(KIND[v.kind] || v.kind)} · <span style="color:var(--dim)">${esc(v.id)}</span>` +
    (v.status === "error" && errl ? `<div class="alert err">${esc(errl.replace(/^\[erreur\]\s*/, ""))}</div>` : "");
  $("cancelrow").classList.toggle("hide", !live);
  $("cancel").onclick = () => api("/api/jobs/" + v.id + "/cancel", {}).catch(() => 0);
  const l = $("log");
  l.textContent = v.log;
  if (live || v.status === "error") $("logd").open = v.status === "error";
  l.scrollTop = l.scrollHeight;
  const mp = v.outputs.filter((o) => o.type === "mp4");
  const oth = v.outputs.filter((o) => o.type !== "mp4" && (o.type !== "jpg" || v.kind === "tool"));
  const href = (o) => `/files/${v.id}/${enc(o.path)}`;
  $("out").innerHTML = mp.map((o) => `<div class="v"><video controls preload="metadata" src="${href(o)}"></video>
      <div class="meta">${esc(o.name)} · ${mo(o.size)}</div><a href="${href(o)}?dl=1">Télécharger</a>` +
      (v.kind === "clips" ? ` · <a href="#" class="enh" data-s="job:${v.id}/${enc(o.path)}">Améliorer</a>` : "") + `</div>`).join("");
  document.querySelectorAll("a.enh").forEach((a) => (a.onclick = (e) => { e.preventDefault(); S.enhSrc = a.dataset.s.split("/").map(decodeURIComponent).join("/"); go("atelier"); }));
  const fn = (window.RICH || {})[v.kind];
  const rich = $("rich");
  if (fn && v.status === "done") fn(v, rich, href);
  else rich.innerHTML = "";
  const files = oth.filter((o) => !(fn && /\.json$/.test(o.name)));
  $("extra").innerHTML = (v.clips && v.clips.clips ? clipsTable(v.clips.clips) : "") +
    (files.length ? `<div style="margin-top:12px">${files.map((o) => `<a class="tag" target="_blank" href="${href(o)}">${esc(o.name)}</a>`).join("")}</div>` : "") +
    (v.kind === "clips" && v.status === "done" && mp.length ? `<div class="btn-row"><button class="btn pri" id="topub">🚀 Préparer la publication</button></div>
      <div class="note warn">Voix de synthèse : active l'étiquette « contenu généré par IA » à la publication, vérifie tes droits et relis la traduction.</div>` : "");
  const tp = $("topub");
  if (tp) tp.onclick = () => { S.lastClips = v.id; go("publish"); };
}
function clipsTable(c) {
  return `<h3>Moments choisis</h3><div class="tablewrap"><table><tr><th>#</th><th>Début–fin</th><th>Titre / extrait</th></tr>${c.map((x) =>
    `<tr><td>${esc(x.id ?? "")}</td><td>${Math.round(x.start)}–${Math.round(x.end)} s</td><td><b>${esc(x.title || "")}</b><br>${esc((x.text || "").slice(0, 160))}</td></tr>`).join("")}</table></div>`;
}

/* ------------------------------------------------------------ santé, comptes, historique */
async function refreshHealth() {
  try {
    const h = await api("/api/health");
    S.health = h;
    $("health").innerHTML = `<span class="dot ${h.ffmpeg ? "on" : ""}"></span>${h.ffmpeg ? "FFmpeg prêt" : "FFmpeg introuvable"}`;
  } catch (e) { $("health").textContent = "Serveur injoignable"; }
}
async function refreshAccounts() {
  try { S.accounts = await api("/api/accounts"); } catch (e) { S.accounts = null; }
  const a = S.accounts, b = $("bd-accounts");
  if (b && a) {
    const n = (a.youtube.connected ? 1 : 0) + (a.tiktok.connected ? 1 : 0);
    b.textContent = n + "/2"; b.classList.remove("hide"); b.classList.toggle("ok", n > 0);
  }
  if (PAGES[S.page] && PAGES[S.page].onAccounts) PAGES[S.page].onAccounts();
}
async function loadHistory() {
  try { S.jobs = await api("/api/history"); } catch (e) { S.jobs = []; }
  if (PAGES[S.page] && PAGES[S.page].onHistory) PAGES[S.page].onHistory();
}
function histRow(x) {
  return `<tr><td><a href="#" data-job="${esc(x.id)}">${esc(x.id)}</a></td><td>${esc(KIND[x.kind] || x.kind || "—")}</td><td><span class="st ${x.status}">${LABEL[x.status] || x.status}</span></td></tr>`;
}
function bindHist(el) {
  el.querySelectorAll("a[data-job]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); S.cur = a.dataset.job; go("job", S.cur); }));
}

/* ------------------------------------------------------------ boîte « source vidéo » partagée */
function sourceBox(extra = "") {
  return `<h2>Vidéo source</h2>
    <div class="drop" id="drop" tabindex="0" role="button"><b>Glisse ta vidéo ici</b>ou clique pour choisir un fichier<input id="file" type="file" accept="video/*" hidden></div>
    <div class="bar"><i id="up"></i></div>
    <label for="url">…ou un lien (ta propre vidéo, ou avec autorisation)</label>
    <input id="url" placeholder="https://www.youtube.com/watch?v=…" autocomplete="off">
    <div class="note" id="src">${S.source ? "Fichier prêt : " + esc(S.source.replace(/^[^_]*_/, "")) : "Aucune source."}</div>${extra}`;
}
function bindSource() {
  const d = $("drop");
  if (!d) return;
  d.onclick = () => $("file").click();
  d.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file").click(); } };
  ["dragover", "dragenter"].forEach((e) => d.addEventListener(e, (ev) => { ev.preventDefault(); d.classList.add("on"); }));
  ["dragleave", "drop"].forEach((e) => d.addEventListener(e, (ev) => { ev.preventDefault(); d.classList.remove("on"); }));
  d.addEventListener("drop", (ev) => { if (ev.dataTransfer.files[0]) uploadSource(ev.dataTransfer.files[0]); });
  $("file").onchange = (e) => { if (e.target.files[0]) uploadSource(e.target.files[0]); };
}
function uploadSource(f) {
  $("src").textContent = "Envoi de " + f.name + "…";
  const x = new XMLHttpRequest();
  x.open("POST", "/api/upload?name=" + encodeURIComponent(f.name));
  x.upload.onprogress = (e) => { if (e.lengthComputable) $("up").style.width = (100 * e.loaded / e.total) + "%"; };
  x.onload = () => {
    try {
      const r = JSON.parse(x.responseText);
      if (r.id) { S.source = r.id; S.enhSrc = ""; $("url").value = ""; $("src").textContent = "Prêt : " + f.name + " (" + mo(f.size) + ")"; }
      else { $("src").textContent = r.error || "Échec"; toast(r.error || "Échec de l'envoi.", "err"); }
    } catch (e) { $("src").textContent = "Échec"; }
  };
  x.onerror = () => { $("src").textContent = "Échec de l'envoi"; toast("Échec de l'envoi.", "err"); };
  x.send(f);
}
const currentSource = () => ($("url") && $("url").value.trim()) || S.enhSrc || S.source;

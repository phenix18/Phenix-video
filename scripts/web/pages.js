/* Phenix-video — pages de l'interface (Accueil, Studio, Atelier, Tendances, Profil & niches, Publication, Comptes, Historique, Réglages). */
"use strict";
window.RICH = {};
const opt = (arr) => arr.map(([v, t, sel]) => `<option value="${v}"${sel ? " selected" : ""}>${t}</option>`).join("");
const LANGS = [["", "Garder la langue d'origine"], ["fr", "Français"], ["en", "Anglais"], ["es", "Espagnol"], ["pt", "Portugais"], ["de", "Allemand"], ["ar", "Arabe"]];
const cols = (left, right = resultShell()) => `<div class="cols"><div class="stack">${left}</div><div class="stack">${right}</div></div>`;
const seg = (items, cur) => `<div class="seg" role="tablist">${items.map(([id, t]) => `<button role="tab" data-t="${id}" class="${id === cur ? "on" : ""}">${t}</button>`).join("")}</div>`;
function bindSeg(el, cb) { el.querySelectorAll(".seg button").forEach((b) => (b.onclick = () => cb(b.dataset.t))); }
const txt = (u) => fetch(u).then((r) => (r.ok ? r.text() : ""));

/* ============================================================ ACCUEIL */
PAGES.home = {
  result: false,
  render(el) {
    el.innerHTML = `<section class="hero"><div><h2>Bienvenue sur <span>Phenix-video</span></h2>
      <p>Transforme une vidéo en clips verticaux prêts à publier : sous-titres animés, traduction, doublage, montage — 100 % local et gratuit. Analyse ton profil, trouve ta niche, choisis les bons horaires et poste en direct.</p>
      <div class="btn-row"><button class="btn pri" data-go="studio">🎬 Créer des clips</button><button class="btn" data-go="insights">🎯 Analyser mon profil</button></div></div>
      <img src="/static/img/mascot.png" alt="Mascotte phenix_forever"></section>
      <div class="kpis" id="kpis"></div>
      <h2 class="card-h" style="margin:22px 0 10px">Par où commencer ?</h2>
      <div class="cards">
        ${[["studio", "🎬", "Studio clips & doublage", "Découpe automatique, cadrage visage, sous-titres, voix off."],
          ["atelier", "🛠️", "Atelier de montage", "Effets, fonds, mascotte, jump-cuts, musique, masquer ta marque."],
          ["trends", "📈", "Tendances", "Colle des liens viraux : durée, accroche, hashtags."],
          ["insights", "🎯", "Profil & niches", "Meilleurs jours/heures, niche à viser, planning + agenda."],
          ["publish", "🚀", "Publication", "Titre, description, hashtags, fiche de boost, envoi direct."],
          ["accounts", "🔗", "Comptes", "Connecte YouTube et TikTok pour publier sans quitter l'app."]]
          .map(([id, ic, t, d]) => `<button class="tile" data-go="${id}"><span class="ic">${ic}</span><b>${t}</b><span>${d}</span></button>`).join("")}
      </div>
      <section class="card" style="margin-top:22px"><h2>Derniers travaux</h2><div id="hist" class="note">Chargement…</div></section>`;
    el.querySelectorAll("[data-go]").forEach((b) => (b.onclick = () => go(b.dataset.go)));
  },
  init() { this.onHistory(); this.onAccounts(); },
  onAccounts() {
    const k = $("kpis"); if (!k) return;
    const a = S.accounts, h = S.health;
    k.innerHTML = `<div class="kpi"><small>FFmpeg</small><b>${h ? (h.ffmpeg ? "Prêt" : "Absent") : "…"}</b></div>
      <div class="kpi"><small>YouTube</small><b>${a ? (a.youtube.connected ? "Connecté" : "Non connecté") : "…"}</b></div>
      <div class="kpi"><small>TikTok</small><b>${a ? (a.tiktok.connected ? "Connecté" : "Non connecté") : "…"}</b></div>
      <div class="kpi"><small>Travaux</small><b>${S.jobs.length}</b></div>`;
  },
  onHistory() {
    const h = $("hist"); if (!h) return;
    h.innerHTML = S.jobs.length ? `<table>${S.jobs.slice(0, 6).map(histRow).join("")}</table>` : `<div class="empty"><span class="big">🎞️</span>Aucun travail pour l'instant. Lance ton premier clip depuis le Studio.</div>`;
    bindHist(h); this.onAccounts();
  },
};

/* ============================================================ STUDIO */
PAGES.studio = {
  render(el) {
    el.innerHTML = cols(`
      <section class="card">${sourceBox()}</section>
      <section class="card"><h2>Montage</h2>
        <div class="g2"><div><label for="clips">Nombre de clips</label><input id="clips" type="number" value="5" min="1" max="20"></div>
        <div><label for="aspect">Format</label><select id="aspect">${opt([["9:16", "9:16 (TikTok, Reels, Shorts)"], ["16:9", "16:9"], ["1:1", "1:1"], ["4:5", "4:5"]])}</select></div></div>
        <div class="g2"><div><label for="min">Durée min (s)</label><input id="min" type="number" value="75"></div>
        <div><label for="max">Durée max (s)</label><input id="max" type="number" value="180"></div></div>
        <label class="chk"><input id="short" type="checkbox">Clips courts (20–60 s)</label>
        <label class="chk"><input id="tighten" type="checkbox" checked>Couper les blancs (rythme dynamique)</label>
        <div class="g2"><div><label for="style">Sous-titres</label><select id="style">${opt([["pop", "Pop (mot jaune)"], ["karaoke", "Karaoké"], ["clean", "Bandeau"], ["minimal", "Minimal"]])}</select></div>
        <div><label for="quality">Qualité</label><select id="quality">${opt([["balanced", "Équilibrée"], ["high", "Haute"], ["max", "Maximale"], ["fast", "Rapide"]])}</select></div></div>
      </section>
      <section class="card"><h2>Langue &amp; voix</h2>
        <label for="to">Traduire vers</label><select id="to">${opt(LANGS)}</select>
        <label class="chk"><input id="dub" type="checkbox" checked>Remplacer la voix (voix off de synthèse)</label>
        <div class="g2"><div><label for="voice">Voix</label><select id="voice">${opt([["female", "Féminine"], ["male", "Masculine"], ["both", "Les deux (2 versions)"]])}</select></div>
        <div><label for="bg">Son d'origine</label><select id="bg">${opt([["duck", "Baissé"], ["none", "Supprimé"], ["keep", "Gardé"]])}</select></div></div>
        <button class="btn pri block" id="go">▶ Lancer</button>
        <button class="btn block" id="an">🔍 Analyser seulement (voir les moments choisis)</button>
      </section>`);
  },
  init() {
    bindSource();
    const o = (an) => ({ source: currentSource(), analyse_only: an, clips: $("clips").value, aspect: $("aspect").value, min: $("min").value, max: $("max").value,
      short: $("short").checked, tighten: $("tighten").checked, style: $("style").value, quality: $("quality").value, translate_to: $("to").value,
      dub: $("dub").checked, voice: $("voice").value, bg: $("bg").value });
    const run = (an) => { const x = o(an); if (!x.source) return toast("Ajoute une vidéo ou un lien.", "warn"); runJob("clips", x); };
    $("go").onclick = () => run(false); $("an").onclick = () => run(true);
  },
};

/* ============================================================ ATELIER */
const FX = { vignette: "Vignette", warm: "Chaud", cool: "Froid", cinema: "Cinéma", vivid: "Éclatant", bw: "Noir & blanc", grain: "Grain", sharpen: "Netteté", glitch: "Glitch", shake: "Tremblement", flash: "Flash", zoomin: "Zoom lent", fade: "Fondu", lowlight: "Éclaircir" };
PAGES.atelier = {
  tab: "enh", up: {},
  render(el) {
    const t = this.tab;
    el.innerHTML = cols(`
      <section class="card">${sourceBox(S.enhSrc ? `<div class="alert ok">Clip choisi : <b>${esc(S.enhSrc.split("/").pop())}</b> <a href="#" id="clrsrc">changer</a></div>` : "")}</section>
      ${seg([["enh", "✨ Améliorer"], ["tool", "🧰 Outils"], ["brand", "🛡️ Masquer ma marque"]], t)}
      <section class="card" id="tabbody">${this[t + "Html"]()}</section>`);
  },
  enhHtml() {
    return `<h2>Améliorer la vidéo</h2>
      <label class="chk"><input id="e_clean" type="checkbox" checked>Nettoyer (bruit audio/vidéo, netteté, volume)</label>
      <label for="e_bg">Arrière-plan (personne face caméra)</label>
      <select id="e_bg">${opt([["", "Garder"], ["blur", "Flou"], ["color", "Couleur unie"], ["image", "Image (à téléverser)"]])}</select>
      <div class="g2"><div><label for="e_col">Couleur</label><input id="e_col" type="color" value="#0b1f3a"></div><div><label for="e_img">Image de fond</label><input id="e_img" type="file" accept="image/*"></div></div>
      <label>Effets (plusieurs possibles)</label>
      <div class="g2">${Object.entries(FX).map(([k, v]) => `<label class="chk" style="margin:2px 0"><input type="checkbox" class="fxc" value="${k}">${v}</label>`).join("")}</div>
      <label for="e_title">Titre animé (3 s)</label><input id="e_title" maxlength="80" placeholder="Optionnel">
      <label class="chk"><input id="e_mascot" type="checkbox">Mascotte phenix_forever (pulse avec la voix)</label>
      <div class="g2"><div><label for="e_mpos">Position mascotte</label><select id="e_mpos">${opt([["br", "Bas droite"], ["bl", "Bas gauche"], ["tr", "Haut droite"], ["tl", "Haut gauche"]])}</select></div>
      <div><label for="e_stk">Sticker / GIF (à toi)</label><input id="e_stk" type="file" accept="image/*"></div></div>
      <button class="btn pri block" id="goenh">✨ Améliorer</button>
      <div class="note">Personnages : seulement ta mascotte, la mascotte fournie ou tes propres images (pas de personnages protégés).</div>`;
  },
  toolHtml() {
    return `<h2>Outil de montage</h2>
      <label for="tl">Outil</label><select id="tl">${opt([["trim", "Couper un passage"], ["speed", "Accélérer / ralentir"], ["silence", "Supprimer les blancs (jump-cuts)"],
        ["music", "Ajouter une musique (baisse auto sous la voix)"], ["text", "Titre animé"], ["punch", "Zooms d'emphase"], ["voice", "Changer la voix"], ["loudnorm", "Normaliser le volume"],
        ["logo", "Ajouter MON logo / filigrane"], ["burn", "Incruster des sous-titres (.srt / .ass)"], ["stabilize", "Stabiliser"], ["thumbnail", "Meilleure image de couverture"]])}</select>
      <div id="tl_trim" class="tlf"><div class="g2"><div><label for="tl_start">Début (s ou mm:ss)</label><input id="tl_start" value="0"></div><div><label for="tl_end">Fin (vide = jusqu'au bout)</label><input id="tl_end"></div></div></div>
      <div id="tl_speed" class="tlf hide"><label for="tl_factor">Facteur (1.25 = plus rapide, 0.8 = plus lent)</label><input id="tl_factor" type="number" step="0.05" value="1.25"></div>
      <div id="tl_music" class="tlf hide"><label for="tl_track">Fichier musique (à toi / libre de droits)</label><input id="tl_track" type="file" accept="audio/*"><label for="tl_vol">Volume</label><input id="tl_vol" type="number" step="0.05" value="0.15"></div>
      <div id="tl_text" class="tlf hide"><label for="tl_txt">Texte</label><input id="tl_txt" maxlength="120"><div class="g2"><div><label for="tl_pos">Position</label><select id="tl_pos">${opt([["top", "Haut"], ["center", "Centre"], ["bottom", "Bas"]])}</select></div><div><label for="tl_tstart">Début (s)</label><input id="tl_tstart" value="0"></div></div></div>
      <div id="tl_punch" class="tlf hide"><label for="tl_at">Instants des zooms (secondes, séparées par des virgules)</label><input id="tl_at" placeholder="3, 12, 20"></div>
      <div id="tl_voice" class="tlf hide"><label for="tl_preset">Voix</label><select id="tl_preset">${opt([["deep", "Grave"], ["low", "Un peu plus grave"], ["high", "Plus aiguë"], ["child", "Très aiguë"], ["radio", "Radio"], ["echo", "Écho"], ["robot", "Robot"]])}</select></div>
      <div id="tl_logo" class="tlf hide"><label for="tl_img">Image du logo (PNG conseillé)</label><input id="tl_img" type="file" accept="image/*"><div class="g2"><div><label for="tl_lpos">Position</label><select id="tl_lpos">${opt([["br", "Bas droite"], ["bl", "Bas gauche"], ["tr", "Haut droite"], ["tl", "Haut gauche"], ["center", "Centre"]])}</select></div><div><label for="tl_scale">Taille (0.05–0.6)</label><input id="tl_scale" type="number" step="0.05" value="0.15"></div></div></div>
      <div id="tl_burn" class="tlf hide"><label for="tl_subs">Fichier de sous-titres</label><input id="tl_subs" type="file" accept=".srt,.ass"></div>
      <button class="btn pri block" id="gotl">Appliquer</button>
      <div class="note">Pour assembler plusieurs vidéos avec transitions : <code>./phenix edit concat a.mp4 b.mp4 -o out.mp4 --xfade fade</code>.</div>`;
  },
  brandHtml() {
    return `<h2>Zones de TA marque</h2>
      ${[["tl", "Haut gauche"], ["tr", "Haut droite"], ["bl", "Bas gauche"], ["br", "Bas droite"]].map(([v, t]) => `<label class="chk"><input class="ar" type="checkbox" value="${v}"${v === "br" ? " checked" : ""}>${t}</label>`).join("")}
      <label for="method">Méthode</label><select id="method">${opt([["blur", "Flou"], ["delogo", "Effacement doux"], ["box", "Bandeau noir"]])}</select>
      <button class="btn pri block" id="godl">Masquer</button>
      <div class="alert warn">À utiliser pour ton propre logo ou nom de compte. Ne retire pas le crédit d'un autre créateur : c'est contraire aux règles des plateformes et à son droit d'auteur.</div>`;
  },
  init(el) {
    bindSource(); bindSeg(el, (t) => { this.tab = t; this.render(el); this.init(el); });
    const c = $("clrsrc"); if (c) c.onclick = (e) => { e.preventDefault(); S.enhSrc = ""; this.render(el); this.init(el); };
    const src = () => currentSource();
    const need = () => { if (!src()) { toast("Ajoute une vidéo ou un lien (ou choisis un clip produit).", "warn"); return false; } return true; };
    if (this.tab === "enh") {
      let bgImg = "", stk = "";
      $("e_img").onchange = () => upfile($("e_img"), (i) => (bgImg = i)); $("e_stk").onchange = () => upfile($("e_stk"), (i) => (stk = i));
      $("goenh").onclick = () => {
        if (!need()) return;
        const o = { source: src(), clean: $("e_clean").checked, bg: $("e_bg").value, bg_color: $("e_col").value, bg_image: bgImg,
          effects: [...document.querySelectorAll(".fxc:checked")].map((x) => x.value), title: $("e_title").value, mascot: $("e_mascot").checked, mascot_pos: $("e_mpos").value, sticker: stk, quality: "balanced" };
        if (o.bg === "image" && !bgImg) return toast("Choisis l'image de fond.", "warn");
        runJob("enhance", o);
      };
    } else if (this.tab === "tool") {
      const T = ["trim", "speed", "music", "text", "punch", "voice", "logo", "burn"], up = {};
      $("tl").onchange = () => T.forEach((t) => $("tl_" + t).classList.toggle("hide", $("tl").value !== t));
      [["tl_track", "track"], ["tl_img", "image"], ["tl_subs", "subs"]].forEach(([id, k]) => ($(id).onchange = () => upfile($(id), (i) => (up[k] = i))));
      $("gotl").onclick = () => {
        if (!need()) return;
        const t = $("tl").value;
        const o = { tool: t, source: src(), quality: "balanced", start: $("tl_start").value, end: $("tl_end").value, factor: $("tl_factor").value, volume: $("tl_vol").value, track: up.track,
          text: $("tl_txt").value, position: t === "logo" ? $("tl_lpos").value : $("tl_pos").value, punch: "", at: $("tl_at").value, preset: $("tl_preset").value, image: up.image, scale: $("tl_scale").value, subs: up.subs };
        if (t === "text") o.start = $("tl_tstart").value;
        runJob("tool", o);
      };
    } else {
      $("godl").onclick = () => { if (need()) runJob("delogo", { source: src(), method: $("method").value, areas: [...document.querySelectorAll(".ar:checked")].map((x) => x.value) }); };
    }
  },
};

/* ============================================================ TENDANCES */
PAGES.trends = {
  render(el) {
    el.innerHTML = cols(`<section class="card"><h2>Analyser des vidéos virales</h2>
      <p class="lead">Colle des liens (un par ligne) de vidéos qui marchent dans ta niche. Phenix-video lit les infos publiques (titre, durée, vues, hashtags) et en tire la formule : durée, formes d'accroche, hashtags, idées de titres pour TON sujet. Il ne copie pas les vidéos.</p>
      <label for="tr_links">Liens</label><textarea id="tr_links" rows="5" placeholder="https://www.tiktok.com/@…/video/…&#10;https://www.youtube.com/shorts/…"></textarea>
      <label for="tr_search">…ou recherche YouTube (si aucun lien)</label><input id="tr_search" placeholder="astuces argent">
      <div class="g2"><div><label for="tr_theme">Ton sujet</label><input id="tr_theme" placeholder="l'argent, le football, la cuisine"></div>
      <div><label for="tr_lang">Langue des idées</label><select id="tr_lang">${opt([["fr", "Français"], ["en", "Anglais"]])}</select></div></div>
      <label for="tr_to">Traduire les titres proposés vers</label><select id="tr_to">${opt([["", "Non"], ...LANGS.slice(1)])}</select>
      <label class="chk"><input id="tr_deep" type="checkbox">Analyse approfondie (télécharge en basse définition : accroche parlée + rythme de montage, plus lent)</label>
      <button class="btn pri block" id="gotr">📈 Analyser les tendances</button>
      <div class="note">Ce sont des corrélations, pas une recette garantie. Inspire-toi de la formule, refais ton propre contenu.</div></section>`);
  },
  init() {
    $("gotr").onclick = () => {
      const o = { links: $("tr_links").value, search: $("tr_search").value, theme: $("tr_theme").value, lang: $("tr_lang").value, translate_to: $("tr_to").value, deep: $("tr_deep").checked };
      if (!o.links.trim() && !o.search.trim()) return toast("Colle des liens ou écris une recherche.", "warn");
      runJob("trends", o);
    };
  },
};
RICH.trends = async (v, el, href) => {
  const f = v.outputs.find((o) => o.name === "TENDANCES.md"), g = v.outputs.find((o) => o.name === "idees.md");
  if (!f) return;
  const [a, b] = await Promise.all([txt(href(f)), g ? txt(href(g)) : ""]);
  el.innerHTML = `<pre style="max-height:520px">${esc(a + "\n\n" + b)}</pre>`;
};

/* ============================================================ PROFIL & NICHES */
const DAYS_TZ = `<label for="i_tz">Fuseau horaire (décalage vs UTC)</label><input id="i_tz" type="number" step="0.5" value="0"><div class="note">Ouagadougou = 0 (UTC+0). Les heures affichées sont en heure locale.</div>`;
PAGES.insights = {
  tab: "profile",
  render(el) {
    const t = this.tab;
    const body = {
      profile: `<h2>Analyser un profil</h2><p class="lead">Colle le lien de TON profil (ou d'un concurrent) : Phenix-video lit les vidéos publiques et trouve ce qui marche : jours, heures, durée, accroche, hashtags.</p>
        <label for="i_url">Lien du profil</label><input id="i_url" placeholder="https://www.tiktok.com/@toncompte"><div class="g2"><div><label for="i_n">Vidéos à lire</label><input id="i_n" type="number" value="25" min="5" max="60"></div><div><label for="i_theme">Ton thème (idées)</label><input id="i_theme" placeholder="optionnel"></div></div>
        ${DAYS_TZ}<label for="i_pw">Publications par semaine (planning)</label><input id="i_pw" type="number" value="4" min="1" max="14">
        <button class="btn pri block" id="go_p">🎯 Analyser ce profil</button>`,
      niches: `<h2>Trouver une niche</h2><p class="lead">Compare des thèmes : demande (vues), chances pour un petit compte, fraîcheur. Écris tes mots-clés, ou laisse vide pour tester une liste d'idées de départ.</p>
        <label for="n_kw">Mots-clés (séparés par des virgules)</label><input id="n_kw" placeholder="football, cuisine africaine, finance personnelle">
        <label for="n_n">Vidéos lues par niche</label><input id="n_n" type="number" value="8" min="3" max="20">
        <button class="btn pri block" id="go_n">🔎 Classer les niches</button><div class="note">Plus lent avec beaucoup de mots-clés (une recherche par niche).</div>`,
      plan: `<h2>Planning de publication</h2><p class="lead">${S.lastProfile ? "Construit à partir de ta dernière analyse de profil." : "Pas encore d'analyse de profil : un planning générique (créneaux usuels) sera proposé."}</p>
        ${DAYS_TZ}<label for="i_pw">Publications par semaine</label><input id="i_pw" type="number" value="4" min="1" max="14">
        <label for="i_theme">Ton thème</label><input id="i_theme" placeholder="optionnel">
        <button class="btn pri block" id="go_l">📅 Construire le planning + agenda (.ics)</button>`,
    }[t];
    el.innerHTML = cols(`${seg([["profile", "👤 Mon profil"], ["niches", "🧭 Niches"], ["plan", "📅 Planning"]], t)}<section class="card">${body}</section>
      <div class="alert">Ce sont des <b>corrélations</b> sur des données publiques, pas une garantie de viralité. Plus il y a de vidéos, plus c'est fiable (niveau de confiance affiché). Sur YouTube, les heures ne sont souvent pas publiques : utilise YouTube Studio.</div>`);
  },
  init(el) {
    bindSeg(el, (t) => { this.tab = t; this.render(el); this.init(el); if (S.cur) poll(); });
    const tz = () => ($("i_tz") ? $("i_tz").value : "0");
    if ($("go_p")) $("go_p").onclick = () => { const u = $("i_url").value.trim(); if (!u) return toast("Colle le lien du profil.", "warn");
      runJob("insights_profile", { url: u, n: $("i_n").value, theme: $("i_theme").value, tz: tz(), per_week: $("i_pw").value }); };
    if ($("go_n")) $("go_n").onclick = () => runJob("insights_niches", { keywords: $("n_kw").value, n: $("n_n").value });
    if ($("go_l")) $("go_l").onclick = () => runJob("insights_plan", { job: S.lastProfile, theme: $("i_theme").value, tz: tz(), per_week: $("i_pw").value });
  },
};
function chart(list, unit = "×") {
  if (!list || !list.length) return `<div class="note">Pas assez de données.</div>`;
  const mx = Math.max(1.2, ...list.map((x) => x.lift)), best = Math.max(...list.map((x) => x.lift));
  return `<div class="chart">${list.map((x) => `<div class="crow${x.lift === best && x.lift > 1.05 ? " best" : ""}"><span>${esc(x.label)}</span><div class="tr"><i style="width:${(x.lift / mx * 100).toFixed(1)}%"></i><u style="left:${(1 / mx * 100).toFixed(1)}%"></u></div><small>${unit}${x.lift.toFixed(2)} · ${x.count}</small></div>`).join("")}</div>`;
}
const slotsHtml = (p) => `<div>${p.slots.map((s) => `<div class="slot"><span>${esc(s.weekday)} <small style="color:var(--dim)">${esc(s.date.slice(5))}</small></span><b>${esc(s.local_time)}</b><span>${esc(s.idea)} <small style="color:var(--dim)">· ${esc(s.origin)}</small></span></div>`).join("")}</div>
  <h3>Avant chaque publication</h3><ul class="reco">${p.checklist.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`;
RICH.insights_profile = async (v, el, href) => {
  const f = v.outputs.find((o) => o.name === "insights.json"); if (!f) return;
  const d = await (await fetch(href(f))).json(), s = d.stats, ics = v.outputs.find((o) => o.name === "planning.ics");
  const mdf = v.outputs.find((o) => o.name === "INSIGHTS.md");
  el.innerHTML = `<div class="kpis"><div class="kpi"><small>Vidéos analysées</small><b>${s.count}</b></div><div class="kpi"><small>Vues médianes</small><b>${fmtN(s.views_median)}</b></div>
    <div class="kpi"><small>Cadence</small><b>${s.per_week} /sem</b></div><div class="kpi"><small>Dynamique</small><b>${s.momentum >= 1 ? "↗" : "↘"} ×${s.momentum}</b></div><div class="kpi"><small>Confiance</small><b>${esc(s.confidence)}</b></div></div>
    <h3>Ce que je te conseille</h3><ul class="reco">${d.recommendations.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    <h3>Quand publier</h3>${s.has_hours ? `<div class="note">Heure locale (UTC${s.tz >= 0 ? "+" : ""}${s.tz}). Barre = performance relative à ta médiane ; trait = ta médiane (×1).</div>${chart(s.hours)}` : `<div class="alert warn">Les heures de publication ne sont pas publiques pour ce réseau : seuls les jours sont analysés. Pour YouTube, consulte « Quand vos spectateurs sont en ligne » dans YouTube Studio.</div>`}
    <h3>Meilleurs jours</h3>${chart(s.weekdays)}<h3>Durée</h3>${chart(s.durations)}<h3>Formes d'accroche</h3>${chart(s.hooks)}
    <h3>Hashtags porteurs</h3><div>${(s.hashtags || []).map((h) => `<span class="tag${h.lift > 1.2 ? " hot" : ""}">${esc(h.label)} ×${h.lift.toFixed(2)}</span>`).join("")}</div>
    <h3>Mots qui reviennent dans tes meilleures vidéos</h3><div>${(s.keywords || []).map((h) => `<span class="tag">${esc(h.label)} ×${h.lift.toFixed(2)}</span>`).join("")}</div>
    <h3>Planning de la semaine</h3>${slotsHtml(d.plan)}
    <div class="btn-row">${ics ? `<a class="btn pri" href="${href(ics)}?dl=1">📅 Ajouter à mon agenda (.ics)</a>` : ""}${mdf ? `<a class="btn" target="_blank" href="${href(mdf)}">Rapport complet</a>` : ""}</div>
    <div class="note">Ouvre le fichier .ics avec Google Agenda / Outlook / téléphone : un rappel 30 min avant chaque créneau est inclus.</div>`;
};
RICH.insights_niches = async (v, el, href) => {
  const f = v.outputs.find((o) => o.name === "insights.json"); if (!f) return;
  const d = await (await fetch(href(f))).json();
  el.innerHTML = d.niches.length ? `<p class="lead">Classées par potentiel pour un compte qui démarre.</p><div class="stack">${d.niches.map((n, i) => `<div class="card niche"><div class="sc"><div class="score" style="--p:${n.score}"><span>${n.score}</span></div>
      <div><b style="font-size:16px">${i + 1}. ${esc(n.keyword)}</b><div class="note" style="margin:0">${n.sample} vidéos lues · ${fmtN(n.views_median)} vues médianes · ~${Math.round(n.duration_median)} s · engagement ${(n.engagement_median * 100).toFixed(1)} %</div></div></div>
      <div class="note" style="margin:0">Petits comptes qui percent : <b>${Math.round(n.small_channel_win_rate * 100)} %</b> · Contenu récent : <b>${Math.round(n.fresh_share * 100)} %</b></div>
      <div>${(n.sub_niches || []).map((s) => `<span class="tag hot">${esc(s)}</span>`).join("")}${(n.hashtags || []).slice(0, 5).map((s) => `<span class="tag">${esc(s)}</span>`).join("")}</div>
      <details><summary>Idées de titres vues dans cette niche</summary><ul class="reco">${(n.titles || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details></div>`).join("")}</div>`
    : `<div class="empty">Aucune niche exploitable.</div>`;
};
RICH.insights_plan = async (v, el, href) => {
  const f = v.outputs.find((o) => o.name === "plan.json"), ics = v.outputs.find((o) => o.name === "planning.ics"); if (!f) return;
  const p = await (await fetch(href(f))).json();
  el.innerHTML = `<h3>Planning de la semaine</h3>${slotsHtml(p)}<div class="btn-row">${ics ? `<a class="btn pri" href="${href(ics)}?dl=1">📅 Ajouter à mon agenda (.ics)</a>` : ""}</div>`;
};

/* ============================================================ PUBLICATION */
PAGES.publish = {
  folders: [], job: "",
  render(el) {
    const a = S.accounts, yt = a && a.youtube.connected, tt = a && a.tiktok.connected;
    el.innerHTML = cols(`
      <section class="card"><h2>1. Dossier de publication</h2>
        <p class="lead">Prépare pour chaque clip : titre, description, hashtags, fiche de boost et réglages (étiquette IA comprise).</p>
        <label for="pj">Travail de clips</label><select id="pj"></select>
        <label for="ph">Ton @ (optionnel, pour les mentions)</label><input id="ph" placeholder="@toncompte">
        <button class="btn pri block" id="gopub">📦 Préparer le dossier</button><div class="note" id="pubnote"></div></section>
      <section class="card" id="sendcard"><h2>2. Envoi direct</h2><div id="sendbody" class="note">Prépare d'abord le dossier.</div></section>`);
  },
  init() { this.onHistory(); this.onAccounts(); },
  onHistory() {
    const sel = $("pj"); if (!sel) return;
    const cl = S.jobs.filter((j) => j.kind === "clips" && j.status === "done");
    sel.innerHTML = cl.length ? cl.map((j) => `<option value="${esc(j.id)}"${j.id === (S.lastClips || this.job) ? " selected" : ""}>${esc(j.id)}</option>`).join("") : `<option value="">Aucun clip terminé</option>`;
    sel.onchange = () => this.load();
    $("gopub").onclick = () => { if (!sel.value) return toast("Crée d'abord des clips dans le Studio.", "warn"); runJob("publish", { job: sel.value, handle: $("ph").value }, { keep: false }); this.watch(sel.value); };
    this.load();
  },
  watch(id) { clearInterval(this.t); this.t = setInterval(() => { if (S.page !== "publish") return clearInterval(this.t); fetch("/api/jobs/" + S.cur).then((r) => r.json()).then((v) => { if (v.status === "done" || v.status === "error") { clearInterval(this.t); this.load(); } }); }, 2000); },
  async load() {
    const sel = $("pj"); if (!sel || !sel.value) return;
    this.job = sel.value;
    const v = await fetch("/api/jobs/" + this.job).then((r) => r.json()).catch(() => null);
    if (!v || v.error) return;
    this.folders = [...new Set(v.outputs.filter((o) => /^out\/publish\/[^/]+\/youtube\.txt$/.test(o.path)).map((o) => o.path.split("/")[2]))];
    this.boost = v.outputs.find((o) => o.name === "BOOST.md");
    $("pubnote").textContent = this.folders.length ? this.folders.length + " dossier(s) prêt(s) dans jobs/" + this.job + "/out/publish" : "Pas encore de dossier de publication pour ce travail.";
    this.onAccounts();
  },
  onAccounts() {
    const b = $("sendbody"); if (!b) return;
    if (!this.folders.length) { b.className = "note"; b.textContent = "Prépare d'abord le dossier."; return; }
    const a = S.accounts || { youtube: {}, tiktok: {} }, yt = a.youtube.connected, tt = a.tiktok.connected;
    b.className = "";
    b.innerHTML = `<label for="pf">Clip</label><select id="pf">${this.folders.map((f) => `<option>${esc(f)}</option>`).join("")}</select>
      ${this.boost ? `<div class="note"><a target="_blank" href="/files/${this.job}/${enc(this.boost.path)}">Ouvrir la fiche de boost (BOOST.md)</a></div>` : ""}
      <h3><span class="dot ${yt ? "on" : ""}"></span>YouTube ${yt ? "· " + esc((a.youtube.profile || {}).title || "connecté") : ""}</h3>
      ${yt ? `<label for="ypriv">Visibilité</label><select id="ypriv">${opt([["private", "Privé (conseillé)"], ["unlisted", "Non répertorié"], ["public", "Public"]])}</select><button class="btn pri block" id="goyt">▶ Envoyer sur YouTube</button>`
        : `<div class="alert">Compte non connecté. <a href="#" data-go="accounts">Connecter YouTube</a></div>`}
      <h3><span class="dot ${tt ? "on" : ""}"></span>TikTok ${tt && a.tiktok.nickname ? "· " + esc(a.tiktok.nickname) : ""}</h3>
      ${tt ? `<label for="tmode">Mode</label><select id="tmode">${opt([["inbox", "Brouillon dans l'app TikTok (conseillé)"], ["direct", "Publication directe (audit TikTok requis)"]])}</select>
        <label for="tpriv">Visibilité (publication directe)</label><select id="tpriv">${opt([["SELF_ONLY", "Moi seul (obligatoire avant audit)"], ["MUTUAL_FOLLOW_FRIENDS", "Amis"], ["FOLLOWER_OF_CREATOR", "Abonnés"], ["PUBLIC_TO_EVERYONE", "Public"]])}</select>
        <label for="tcap">Légende (vide = celle du dossier)</label><textarea id="tcap" rows="3" maxlength="2200"></textarea>
        <button class="btn pri block" id="gott">▶ Envoyer à TikTok</button>`
        : `<div class="alert">Compte non connecté. <a href="#" data-go="accounts">Connecter TikTok</a></div>`}
      <div class="note warn">Voix de synthèse : l'étiquette « contenu généré par IA » est déclarée automatiquement à l'envoi.</div>`;
    b.querySelectorAll("[data-go]").forEach((x) => (x.onclick = (e) => { e.preventDefault(); go(x.dataset.go); }));
    if ($("goyt")) $("goyt").onclick = () => runJob("youtube", { job: this.job, folder: $("pf").value, privacy: $("ypriv").value }, { keep: false });
    if ($("gott")) $("gott").onclick = () => runJob("tiktok", { job: this.job, folder: $("pf").value, mode: $("tmode").value, privacy: $("tpriv").value, caption: $("tcap").value }, { keep: false });
  },
};
RICH.publish = (v, el, href) => { el.innerHTML = `<div class="alert ok">Dossier prêt. Ouvre les fichiers ci-dessous (titre, description, hashtags, fiche de boost) ou va dans « Publication » pour envoyer en direct.</div>`; };

/* ============================================================ COMPTES */
PAGES.accounts = {
  result: true,
  render(el) {
    el.innerHTML = cols(`<div id="acc" class="stack"><div class="card note">Chargement…</div></div>`);
  },
  init() { refreshAccounts(); },
  onAccounts() {
    const a = S.accounts, box = $("acc"); if (!box) return;
    if (!a) { box.innerHTML = `<div class="alert err">Impossible de lire l'état des comptes.</div>`; return; }
    const y = a.youtube, t = a.tiktok, redirect = location.origin + "/tiktok/callback";
    box.innerHTML = `
    <section class="card"><div class="acct"><div class="logo">▶️</div><div style="flex:1"><h2 style="margin-bottom:4px">YouTube</h2>
      <div><span class="dot ${y.connected ? "on" : ""}"></span>${y.connected ? "Connecté : <b>" + esc((y.profile || {}).title || "chaîne") + "</b>" : "Non connecté"}</div>
      <p class="note">Gratuit : crée un « ID client OAuth — Application de bureau » dans Google Cloud (API YouTube Data v3 activée), télécharge le JSON et envoie-le ici. Une fenêtre Google s'ouvre ensuite pour autoriser.</p>
      <label for="secret">Fichier client_secret.json ${S.health && S.health.youtube_ready ? "<span class='tag'>présent ✓</span>" : ""}</label><input id="secret" type="file" accept=".json">
      <div class="btn-row"><button class="btn pri" id="ytlogin">Connecter YouTube</button>${y.connected ? `<button class="btn danger" id="ytout">Déconnecter</button>` : ""}</div>
      <p class="note">Tant que l'app Google est en mode « test », ajoute ton adresse comme utilisateur test. Les envois non audités par Google peuvent rester privés.</p></div></div></section>
    <section class="card"><div class="acct"><div class="logo">🎵</div><div style="flex:1"><h2 style="margin-bottom:4px">TikTok</h2>
      <div><span class="dot ${t.connected ? "on" : ""}"></span>${t.connected ? "Connecté : <b>" + esc(t.nickname || "compte") + "</b>" : t.app_configured ? "App configurée, compte non connecté" : "Non configuré"}</div>
      <p class="note">TikTok demande une « app développeur » gratuite (developers.tiktok.com) avec le produit <i>Login Kit</i> + <i>Content Posting API</i>. Colle ici ses identifiants ; l'adresse de redirection doit être déclarée identique dans l'app.</p>
      <label for="tk_key">Client key</label><input id="tk_key" value="${esc(t.client_key || "")}" autocomplete="off">
      <label for="tk_sec">Client secret</label><input id="tk_sec" type="password" placeholder="${t.app_configured ? "•••••• (enregistré)" : ""}" autocomplete="off">
      <label for="tk_red">Adresse de redirection</label><input id="tk_red" value="${esc(t.redirect_uri || redirect)}">
      <div class="btn-row"><button class="btn" id="tksave">Enregistrer</button></div>
      <label class="chk"><input id="tk_pub" type="checkbox">Autoriser aussi la publication directe (nécessite l'audit TikTok)</label>
      <div class="btn-row"><button class="btn pri" id="tkconn"${t.app_configured ? "" : " disabled"}>Connecter TikTok</button>${t.connected ? `<button class="btn danger" id="tkout">Déconnecter</button>` : ""}</div>
      <div id="tkwait" class="note"></div>
      <details><summary>Si la redirection automatique échoue</summary><label for="tk_code">Colle l'adresse complète (ou le code) affichée par TikTok</label><input id="tk_code" placeholder="http://localhost:8765/tiktok/callback?code=…&amp;state=…"><div class="btn-row"><button class="btn sm" id="tkcode">Valider</button></div></details>
      <div class="alert warn">Avant l'audit TikTok, la publication directe n'est possible qu'en « Moi seul » ; le mode brouillon (inbox) fonctionne et tu termines la publication dans l'app TikTok.</div></div></div></section>
    <section class="card"><h2>Sécurité</h2><p class="note" style="margin:0">Les jetons restent sur cet ordinateur (fichiers protégés dans ton dossier de cache). Rien n'est envoyé ailleurs qu'à YouTube / TikTok. Ces boutons ne fonctionnent que depuis l'ordinateur qui exécute Phenix-video, pas depuis un téléphone en mode réseau local.</p></section>`;
    $("secret").onchange = safe(async () => { const f = $("secret").files[0]; if (!f) return; await api("/api/secret", await f.text()); toast("client_secret.json enregistré.", "ok"); refreshHealth().then(refreshAccounts); });
    $("ytlogin").onclick = () => runJob("yt_login", {}, { keep: false });
    if ($("ytout")) $("ytout").onclick = safe(async () => { await api("/api/accounts/youtube/logout", {}); toast("YouTube déconnecté.", "ok"); refreshAccounts(); });
    $("tksave").onclick = safe(async () => { await api("/api/accounts/tiktok/config", { client_key: $("tk_key").value, client_secret: $("tk_sec").value, redirect_uri: $("tk_red").value }); toast("App TikTok enregistrée.", "ok"); refreshAccounts(); });
    $("tkconn").onclick = safe(async () => {
      const r = await api("/api/accounts/tiktok/connect", { modes: $("tk_pub").checked ? ["upload", "publish"] : ["upload"] });
      $("tkwait").innerHTML = `Fenêtre TikTok ouverte… <a target="_blank" rel="noopener" href="${esc(r.url)}">la rouvrir</a>`;
      let n = 0; const iv = setInterval(async () => { await refreshAccounts(); if ((S.accounts && S.accounts.tiktok.connected) || ++n > 60 || S.page !== "accounts") clearInterval(iv); }, 2000);
    });
    if ($("tkout")) $("tkout").onclick = safe(async () => { await api("/api/accounts/tiktok/logout", {}); toast("TikTok déconnecté.", "ok"); refreshAccounts(); });
    $("tkcode").onclick = safe(async () => { await api("/api/accounts/tiktok/complete", { value: $("tk_code").value }); toast("TikTok connecté.", "ok"); refreshAccounts(); });
  },
};

/* ============================================================ HISTORIQUE / JOB / RÉGLAGES */
PAGES.history = {
  result: false,
  render(el) { el.innerHTML = `<section class="card"><h2>Derniers travaux</h2><div id="hist"></div></section>`; },
  init() { loadHistory(); },
  onHistory() { const h = $("hist"); if (!h) return; h.innerHTML = S.jobs.length ? `<table><tr><th>Travail</th><th>Type</th><th>État</th></tr>${S.jobs.map(histRow).join("")}</table>` : `<div class="empty"><span class="big">🗂️</span>Aucun travail.</div>`; bindHist(h); },
};
PAGES.job = {
  render(el) { el.innerHTML = `<div class="cols one">${resultShell()}</div><div class="btn-row"><button class="btn" id="back">← Retour</button></div>`; },
  init() { $("resbox").classList.remove("hide"); $("back").onclick = () => go("history"); poll(); },
};
PAGES.settings = {
  render(el) {
    el.innerHTML = cols(`<section class="card"><h2>Diagnostic</h2><p class="lead">Vérifie FFmpeg, Python, les modèles et les modules installés.</p>
        <div class="btn-row"><button class="btn" id="godoc">🩺 Vérifier l'installation</button><button class="btn" id="gotest">🧪 Auto-test (1 à 3 min)</button></div></section>
      <section class="card"><h2>Apparence</h2><div class="btn-row"><button class="btn" data-th="dark">🌙 Sombre</button><button class="btn" data-th="light">☀️ Clair</button></div></section>
      <section class="card"><h2>À propos</h2><div id="about" class="note"></div></section>`);
  },
  init(el) {
    $("godoc").onclick = () => runJob("doctor", {}, { keep: false }); $("gotest").onclick = () => runJob("selftest", {}, { keep: false });
    el.querySelectorAll("[data-th]").forEach((b) => (b.onclick = () => setTheme(b.dataset.th)));
    const h = S.health; $("about").innerHTML = h ? `Version <b>${esc(h.version)}</b> · Python ${esc(h.python)} · FFmpeg ${h.ffmpeg ? "✓" : "✗"}<br>Dossier de travail : <code>${esc(h.workdir)}</code><br>© 2026 Phenix - kcw` : "…";
  },
};
function setTheme(t) { document.documentElement.dataset.theme = t; store.set("pv_theme", t); }

#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Interface web LOCALE pour Phenix-video (© 2026 Phenix - kcw) (aucune dépendance en plus de la bibliothèque standard).

  python3 -I scripts/app.py            ->  http://127.0.0.1:8765
  python3 -I scripts/app.py --port 9000 --workdir D:/Studio

Tout reste sur ta machine : le serveur n'écoute que 127.0.0.1, rien n'est envoyé ailleurs.
Les traitements sont ceux de pipeline.py / edit.py, lancés en sous-processus ; le journal s'affiche en direct.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import hmac
import html
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"
sys.path.insert(0, str(HERE))
import accounts  # noqa: E402
from common import StudioError  # noqa: E402
MAX_UPLOAD = 8 * 1024 ** 3  # 8 Go
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
# Mode réseau local (--lan) : accès depuis un téléphone du même Wi-Fi, protégé par un code PIN.
LAN = False
PIN = ""
TOKENS: set[str] = set()
FAILS: dict[str, tuple[int, float]] = {}  # ip -> (échecs, bloqué jusqu'à)

MANIFEST = json.dumps({"name": "Phenix-video", "short_name": "Phenix", "start_url": "/", "display": "standalone",
                       "background_color": "#0e1016", "theme_color": "#ff7a18",
                       "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                                 {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"}]})
SW = "self.addEventListener('fetch',()=>{});"  # service worker minimal : rend l'application installable
LOGIN = ('<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         '<title>Phenix-video</title><link rel="manifest" href="/manifest.webmanifest"><link rel="icon" href="/favicon.png"><meta name="theme-color" content="#ff7a18">'
         '<style>body{margin:0;background:#0f1115;color:#e8eaf0;font:16px system-ui;display:grid;place-items:center;min-height:100vh}'
         'form{background:#181b22;border:1px solid #2a2f3a;border-radius:14px;padding:24px;width:min(320px,90vw);text-align:center}'
         'input{width:100%;padding:12px;border-radius:8px;border:1px solid #2a2f3a;background:#0f1218;color:#fff;font-size:22px;'
         'text-align:center;letter-spacing:.3em;box-sizing:border-box}button{margin-top:14px;width:100%;padding:12px;border:0;'
         'border-radius:8px;background:#f5b301;font-weight:700;font-size:16px}p{color:#8b93a7;font-size:13px}#e{color:#ff5d5d}</style></head>'
         '<body><form id="f"><h2>Phenix-video</h2><p>Entre le code affiché sur l\'ordinateur</p>'
         '<input id="p" inputmode="numeric" autocomplete="one-time-code" maxlength="12" autofocus><button>Entrer</button><p id="e"></p></form>'
         '<script>f.onsubmit=async e=>{e.preventDefault();const r=await fetch("/api/login",{method:"POST",body:JSON.stringify({pin:p.value})});'
         'if(r.ok)location.reload();else{const j=await r.json().catch(()=>({}));document.getElementById("e").textContent=j.error||"Code incorrect"}}</script>'
         '</body></html>')


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("10.255.255.255", 1))  # aucun paquet envoyé : sert à connaître l'interface sortante
            return sk.getsockname()[0]
    except OSError:
        return "127.0.0.1"

# --------------------------------------------------------------------------- jobs
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()
WORKDIR = Path.home() / "PhenixVideo"
try:
    VERSION = (HERE.parent / "VERSION").read_text(encoding="utf-8").strip()
except OSError:
    VERSION = "?"


def safe_name(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^\w.\- ]+", "_", name, flags=re.UNICODE).strip(" .") or "video"
    return name[-120:]


def job_dir(job_id: str) -> Path:
    return WORKDIR / "jobs" / job_id


def choice(value, allowed, default):
    return value if value in allowed else default


def num(value, default, lo, hi):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, v))


def build_command(kind: str, opt: dict, out_dir: Path) -> list[str]:
    py = [sys.executable, "-I"]
    if kind == "publish":
        jid = opt.get("job", "")
        if not re.fullmatch(r"[\w-]+", jid) or not (job_dir(jid) / "out").is_dir():
            raise ValueError("Travail introuvable : lance d'abord un traitement de clips.")
        cmd = [*py, str(HERE / "publish.py"), str(job_dir(jid) / "out")]
        if opt.get("handle"):
            cmd += ["--handle", str(opt["handle"])[:60]]
        return cmd
    if kind in ("doctor", "selftest"):
        return [*py, str(HERE / f"{kind}.py")]
    if kind == "youtube":
        jid, folder = opt.get("job", ""), opt.get("folder", "")
        base = (job_dir(jid) / "out" / "publish") if re.fullmatch(r"[\w-]+", jid) else None
        target = (base / folder).resolve() if base else None
        if not target or base.resolve() not in target.parents or not (target / "video.mp4").is_file():
            raise ValueError("Dossier de publication introuvable : prépare d'abord le dossier de publication.")
        secret = WORKDIR / "client_secret.json"
        if not secret.is_file():
            raise ValueError("Ajoute d'abord ton fichier client_secret.json (onglet Réglages).")
        return [*py, str(HERE / "youtube_upload.py"), "--from-folder", str(target), "--client-secret", str(secret),
                "--privacy", choice(opt.get("privacy"), ["private", "unlisted", "public"], "private")]
    if kind == "yt_login":
        secret = WORKDIR / "client_secret.json"
        if not secret.is_file():
            raise ValueError("Ajoute d'abord ton fichier client_secret.json (page Comptes).")
        return [*py, str(HERE / "youtube_upload.py"), "--login", "--client-secret", str(secret)]
    if kind == "tiktok":
        jid, folder = opt.get("job", ""), opt.get("folder", "")
        base = (job_dir(jid) / "out" / "publish") if re.fullmatch(r"[\w-]+", jid) else None
        target = (base / folder).resolve() if base else None
        if not target or base.resolve() not in target.parents or not (target / "video.mp4").is_file():
            raise ValueError("Dossier de publication introuvable : prépare d'abord le dossier de publication.")
        cmd = [*py, str(HERE / "tiktok_upload.py"), "--from-folder", str(target),
               "--mode", choice(opt.get("mode"), ["inbox", "direct"], "inbox"),
               "--privacy", choice(opt.get("privacy"), ["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"], "SELF_ONLY")]
        if opt.get("caption"):
            cmd += ["--caption", str(opt["caption"])[:2200]]
        return cmd
    if kind in ("insights_profile", "insights_niches", "insights_plan"):
        sub = kind.split("_", 1)[1]
        cmd = [*py, str(HERE / "insights.py"), sub,
               "-o", str(out_dir / "analyse"), "--tz", str(num(opt.get("tz"), 0, -12, 14)),
               "--per-week", str(int(num(opt.get("per_week"), 4, 1, 14)))]
        if opt.get("theme"):
            cmd += ["--theme", str(opt["theme"])[:80]]
        if sub == "profile":
            url = str(opt.get("url", "")).strip()
            if not re.match(r"^https?://", url):
                raise ValueError("Colle le lien du profil (https://…).")
            cmd += ["--n", str(int(num(opt.get("n"), 25, 5, 60))), url]
        elif sub == "niches":
            kw = str(opt.get("keywords", "")).strip()[:300]
            cmd += ["--n", str(int(num(opt.get("n"), 8, 3, 20)))]
            cmd += ["--keywords", kw] if kw else ["--seeds"]
        else:
            jid = opt.get("job", "")
            src = job_dir(jid) / "analyse" / "insights.json" if re.fullmatch(r"[\w-]+", str(jid)) else None
            if src and src.is_file():
                cmd += ["--from-json", str(src)]  # sinon : planning générique (créneaux usuels)
        return cmd
    if kind == "trends":
        links = [l.strip() for l in re.split(r"[\s,]+", str(opt.get("links", ""))) if l.strip()][:30]
        if any(not re.match(r"^https?://", l) for l in links):
            raise ValueError("Chaque lien doit commencer par http:// ou https://")
        search = str(opt.get("search", "")).strip()[:120]
        if not links and not search:
            raise ValueError("Colle au moins un lien, ou écris une recherche.")
        cmd = [*py, str(HERE / "trends.py"), "-o", str(out_dir / "tendances"),
               "--theme", str(opt.get("theme", ""))[:80], "--lang", choice(opt.get("lang"), ["fr", "en"], "fr")]
        if opt.get("translate_to") in ("fr", "en", "es", "pt", "de", "ar"):
            cmd += ["--translate-to", opt["translate_to"]]
        if opt.get("deep"):
            cmd += ["--deep"]
        if search and not links:
            cmd += ["--search", search, "--n", "10"]
        return [*cmd, "--", *links] if links else cmd
    src = opt.get("source", "").strip()
    if not src:
        raise ValueError("Aucune vidéo ni lien fourni.")
    if src.startswith("job:"):
        jid, _, rel = src[4:].partition("/")
        base = job_dir(jid).resolve()
        target = (base / rel).resolve()
        if not re.fullmatch(r"[\w-]+", jid) or base not in target.parents or not target.is_file():
            raise ValueError("Clip introuvable.")
        source = str(target)
    elif re.match(r"^https?://", src):
        source = src
    else:
        source = str(WORKDIR / "uploads" / safe_name(src))
        if not Path(source).is_file():
            raise ValueError("Fichier téléversé introuvable.")

    if kind == "tool":
        tool = opt.get("tool", "")
        ext = {"thumbnail": "cover.jpg"}.get(tool, "resultat.mp4")
        q = choice(opt.get("quality"), ["max", "high", "balanced", "fast"], "balanced")
        cmd = [*py, str(HERE / "edit.py"), tool, source, "-o", str(out_dir / ext), "--quality", q]

        def up(key, label, exts):
            f = WORKDIR / "uploads" / safe_name(opt.get(key, ""))
            if not opt.get(key) or not f.is_file() or f.suffix.lower() not in exts:
                raise ValueError(f"{label} non téléversé(e).")
            return str(f)
        if tool == "trim":
            cmd += ["--start", str(opt.get("start") or "0")]
            if opt.get("end"):
                cmd += ["--end", str(opt["end"])]
        elif tool == "speed":
            cmd += ["--factor", str(num(opt.get("factor"), 1.25, 0.25, 4))]
        elif tool == "silence":
            pass
        elif tool == "music":
            cmd += ["--track", up("track", "Musique", (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")),
                    "--volume", str(num(opt.get("volume"), 0.15, 0.02, 1))]
        elif tool == "text":
            if not str(opt.get("text", "")).strip():
                raise ValueError("Écris le texte du titre.")
            cmd += ["--text", str(opt["text"])[:120], "--position", choice(opt.get("position"), ["top", "center", "bottom"], "top"),
                    "--start", str(opt.get("start") or "0"), "--box"]
            if opt.get("end"):
                cmd += ["--end", str(opt["end"])]
        elif tool == "punch":
            at = ",".join(x for x in re.split(r"[,\s]+", str(opt.get("at", ""))) if re.fullmatch(r"\d+(\.\d+)?", x))
            if not at:
                raise ValueError("Indique les instants (en secondes) des zooms, ex. 3,12,20.")
            cmd += ["--at", at]
        elif tool == "voice":
            cmd += ["--preset", choice(opt.get("preset"), ["deep", "low", "high", "child", "radio", "echo", "robot"], "deep")]
        elif tool == "loudnorm" or tool == "stabilize":
            pass
        elif tool == "logo":
            cmd += ["--image", up("image", "Logo", (".png", ".jpg", ".jpeg", ".webp")),
                    "--position", choice(opt.get("position"), ["tl", "tr", "bl", "br", "center"], "br"),
                    "--scale", str(num(opt.get("scale"), 0.15, 0.05, 0.6))]
        elif tool == "burn":
            cmd += ["--subs", up("subs", "Sous-titres", (".srt", ".ass"))]
        elif tool == "thumbnail":
            pass
        else:
            raise ValueError("Outil inconnu.")
        return cmd

    if kind == "enhance":
        cmd = [*py, str(HERE / "enhance.py"), source, "-o", str(out_dir / "ameliore.mp4"),
               "--quality", choice(opt.get("quality"), ["max", "high", "balanced", "fast"], "balanced")]
        if opt.get("clean"):
            cmd += ["--clean"]
        bgk = choice(opt.get("bg"), ["", "blur", "color", "image"], "")
        if bgk == "blur":
            cmd += ["--bg", "blur"]
        elif bgk == "color":
            col = opt.get("bg_color", "#0B1F3A")
            cmd += ["--bg", "color:" + (col if re.fullmatch(r"#[0-9a-fA-F]{6}", col) else "#0B1F3A")]
        elif bgk == "image":
            img = WORKDIR / "uploads" / safe_name(opt.get("bg_image", ""))
            if not img.is_file():
                raise ValueError("Image de fond non téléversée.")
            cmd += ["--bg", f"image:{img}"]
        effs = [e for e in opt.get("effects", []) if re.fullmatch(r"[a-z]+", e)]
        if effs:
            cmd += ["--effects", ",".join(effs)]
        if opt.get("title"):
            cmd += ["--title", str(opt["title"])[:80]]
        if opt.get("mascot"):
            cmd += ["--mascot", "--mascot-position", choice(opt.get("mascot_pos"), ["br", "bl", "tr", "tl", "bc"], "br")]
        if opt.get("sticker"):
            img = WORKDIR / "uploads" / safe_name(opt["sticker"])
            if not img.is_file():
                raise ValueError("Sticker non téléversé.")
            cmd += ["--sticker", f"{img}@{choice(opt.get('sticker_pos'), ['tl', 'tr', 'bl', 'br'], 'tr')},0.2,0,"
                    + str(num(opt.get('sticker_end'), 999, 1, 9999))]
        return cmd

    if kind == "delogo":
        areas = [a for a in opt.get("areas", []) if re.fullmatch(r"(tl|tr|bl|br|\d+,\d+,\d+,\d+)", a)]
        if not areas:
            raise ValueError("Choisis au moins une zone à masquer.")
        cmd = [*py, str(HERE / "edit.py"), "delogo", source, "-o", str(out_dir / "sans_ma_marque.mp4"),
               "--method", choice(opt.get("method"), ["blur", "delogo", "box"], "blur"),
               "--quality", choice(opt.get("quality"), ["max", "high", "balanced", "fast"], "balanced")]
        for a in areas:
            cmd += ["--area", a]
        return cmd

    cmd = [*py, str(HERE / "pipeline.py"), source, "-o", str(out_dir / "out")]
    if opt.get("analyse_only"):
        cmd += ["--stop-after", "clips"]
    cmd += ["--clips", str(int(num(opt.get("clips"), 5, 1, 20)))]
    if opt.get("short"):
        cmd += ["--short"]
    else:
        cmd += ["--min", str(num(opt.get("min"), 75, 10, 600)), "--max", str(num(opt.get("max"), 180, 15, 900))]
    cmd += ["--aspect", choice(opt.get("aspect"), ["9:16", "16:9", "1:1", "4:5"], "9:16"),
            "--mode", choice(opt.get("mode"), ["auto", "track", "center", "blur", "fit", "none"], "auto"),
            "--style", choice(opt.get("style"), ["pop", "karaoke", "clean", "minimal"], "pop"),
            "--quality", choice(opt.get("quality"), ["max", "high", "balanced", "fast"], "balanced"),
            "--model", choice(opt.get("model"), ["tiny", "base", "small", "medium"], "small")]
    target = choice(opt.get("translate_to"), ["", "fr", "en", "es", "pt", "de", "ar"], "")
    if target:
        cmd += ["--translate-to", target]
        if opt.get("dub"):
            cmd += ["--dub", "--voice-gender", choice(opt.get("voice"), ["female", "male", "both"], "female"),
                    "--bg", choice(opt.get("bg"), ["duck", "none", "keep"], "duck")]
    if opt.get("tighten"):
        cmd += ["--tighten"]
    if opt.get("no_captions"):
        cmd += ["--no-captions"]
    return cmd


def run_job(job_id: str) -> None:
    job = JOBS[job_id]
    d = job_dir(job_id)
    log_path = d / "log.txt"
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            log.write("$ " + " ".join(job["cmd"]) + "\n")
            log.flush()
            env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
            proc = subprocess.Popen(job["cmd"], stdout=log, stderr=subprocess.STDOUT, cwd=str(d), env=env)
            job["proc"] = proc
            job["status"] = "running"
            code = proc.wait()
        job["status"] = "cancelled" if job.get("cancel") else ("done" if code == 0 else "error")
    except Exception as exc:  # noqa: BLE001 - on remonte l'erreur dans le journal
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(f"\n[erreur interne] {exc}\n")
        job["status"] = "error"
    finally:
        job["ended"] = time.time()
        job.pop("proc", None)


def start_job(kind: str, opt: dict) -> str:
    job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    d = job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    cmd = build_command(kind, opt, d)
    (d / "options.json").write_text(json.dumps({"kind": kind, **opt}, ensure_ascii=False, indent=1), encoding="utf-8")
    with LOCK:
        JOBS[job_id] = {"id": job_id, "kind": kind, "cmd": cmd, "status": "queued", "started": time.time()}
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    return job_id


def list_outputs(job_id: str) -> list[dict]:
    d = job_dir(job_id)
    res = []
    for p in sorted(d.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix.lower() in (".mp4", ".jpg", ".md", ".json", ".txt", ".ics") and ".tight" not in p.name and p.name != "log.txt" \
                and p.name not in ("options.json",):
            if p.suffix == ".json" and p.name not in ("clips.json", "report.json", "trends.json", "insights.json"):
                continue
            if p.suffix == ".txt" and "publish" not in p.parts:
                continue
            if "publish" in p.parts and p.suffix in (".mp4", ".jpg"):
                continue  # copies déjà listées parmi les clips
            rel = p.relative_to(d).as_posix()
            res.append({"name": p.name, "path": rel, "size": p.stat().st_size, "type": p.suffix[1:]})
    return res


def job_view(job_id: str) -> dict | None:
    job = JOBS.get(job_id)
    d = job_dir(job_id)
    if not d.is_dir():
        return None
    log = ""
    lp = d / "log.txt"
    if lp.exists():
        log = lp.read_text(encoding="utf-8", errors="replace")[-12000:]
    status = job["status"] if job else "done"
    clips = None
    cj = next(d.rglob("clips.json"), None)
    if cj:
        try:
            clips = json.loads(cj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            clips = None
    kind = (job or {}).get("kind", "")
    if not kind:
        try:
            kind = json.loads((d / "options.json").read_text(encoding="utf-8")).get("kind", "")
        except (OSError, ValueError):
            kind = ""
    return {"id": job_id, "status": status, "log": log, "outputs": list_outputs(job_id), "clips": clips, "kind": kind}


def history() -> list[dict]:
    root = WORKDIR / "jobs"
    out = []
    if root.is_dir():
        for d in sorted(root.iterdir(), reverse=True)[:30]:
            if d.is_dir():
                j = JOBS.get(d.name)
                kind = (j or {}).get("kind", "")
                if not kind:
                    try:
                        kind = json.loads((d / "options.json").read_text(encoding="utf-8")).get("kind", "")
                    except (OSError, ValueError):
                        kind = ""
                out.append({"id": d.name, "status": j["status"] if j else "done", "kind": kind})
    return out


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "PhenixVideo/1.0"

    def log_message(self, fmt, *args):  # silence
        pass

    # -- utilitaires
    def _authed(self) -> bool:
        if not LAN:
            return True
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "pv_auth" and v in TOKENS:
                return True
        return False

    def _login(self) -> None:
        ip = self.client_address[0]
        fails, until = FAILS.get(ip, (0, 0.0))
        if time.time() < until:
            return self._err(429, f"Trop d'essais : attends {int(until - time.time())} s.")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            pin = str(json.loads(self.rfile.read(min(n, 1024)) or b"{}").get("pin", "")).strip()
        except (ValueError, TypeError):
            pin = ""
        if PIN and hmac.compare_digest(pin.encode(), PIN.encode()):
            FAILS.pop(ip, None)
            token = secrets.token_hex(16)
            TOKENS.add(token)
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", f"pv_auth={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        fails += 1
        FAILS[ip] = (fails, time.time() + 60 if fails >= 5 else 0.0)
        self._err(401, "Code incorrect.")

    def _static(self, path: str) -> bool:
        files = {"/manifest.webmanifest": ("application/manifest+json", MANIFEST),
                 "/sw.js": ("application/javascript", SW)}
        if path in ("/icon-192.png", "/icon-512.png", "/favicon.png"):
            png = HERE.parent / "assets" / ("icon-192.png" if path != "/icon-512.png" else "icon-512.png")
            if not png.is_file():
                return False
            body = png.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "max-age=86400")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return True
        if path not in files:
            return False
        ctype, text = files[path]
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def _host_ok(self) -> bool:
        if LAN:  # l'accès est contrôlé par le code PIN, pas par le nom d'hôte
            return True
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0] if not (self.headers.get("Host") or "").startswith("[") \
            else (self.headers.get("Host") or "").split("]")[0] + "]"
        return host in ALLOWED_HOSTS

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _err(self, status, msg):
        self._json({"error": msg}, status)

    # -- routes
    def do_GET(self):  # noqa: N802
        if not self._host_ok():
            return self._err(403, "Hôte refusé.")
        url = urlparse(self.path)
        path = unquote(url.path)
        if self._static(path):
            return
        if path == "/tiktok/callback":  # protégé par l'état PKCE secret ; le navigateur de retour n'a pas toujours le cookie
            return self._tiktok_callback(parse_qs(url.query))
        if not self._authed():
            if path == "/":
                body = LOGIN.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return self._err(401, "Non autorisé.")
        if path == "/":
            try:
                body = (WEB / "index.html").read_text(encoding="utf-8").replace("{{VERSION}}", VERSION).encode("utf-8")
            except OSError:
                return self._err(500, "Interface introuvable (dossier scripts/web manquant).")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path.startswith("/static/"):
            self._serve_static(path[len("/static/"):])
        elif path == "/api/accounts":
            self._json(accounts.status())
        elif path == "/api/history":
            self._json(history())
        elif path == "/api/health":
            self._json({"ffmpeg": bool(shutil.which("ffmpeg")), "workdir": str(WORKDIR), "python": sys.version.split()[0],
                        "version": VERSION, "youtube_ready": (WORKDIR / "client_secret.json").is_file()})
        elif m := re.fullmatch(r"/api/jobs/([\w-]+)", path):
            v = job_view(m.group(1))
            self._json(v) if v else self._err(404, "Travail introuvable.")
        elif m := re.fullmatch(r"/files/([\w-]+)/(.+)", path):
            self._serve_file(job_dir(m.group(1)), m.group(2), download="dl" in parse_qs(url.query))
        else:
            self._err(404, "Introuvable.")

    def do_POST(self):  # noqa: N802
        if not self._host_ok():
            return self._err(403, "Hôte refusé.")
        url = urlparse(self.path)
        path = url.path
        if path == "/api/login" and LAN:
            return self._login()
        if not self._authed():
            return self._err(401, "Non autorisé.")
        try:
            if path == "/api/secret":
                n = int(self.headers.get("Content-Length") or 0)
                if not 0 < n < 200_000:
                    return self._err(400, "Fichier invalide.")
                raw = self.rfile.read(n)
                try:
                    js = json.loads(raw)
                    ok = isinstance(js, dict) and ("installed" in js or "web" in js)
                except ValueError:
                    ok = False
                if not ok:
                    return self._err(400, "Ce n'est pas un client_secret.json de Google (type « application de bureau »).")
                (WORKDIR / "client_secret.json").write_bytes(raw)
                return self._json({"ok": True})
            if path == "/api/upload":
                return self._upload(parse_qs(url.query).get("name", ["video"])[0])
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}")
            if path.startswith("/api/accounts/"):
                return self._accounts_post(path[len("/api/accounts/"):], data)
            if path == "/api/jobs":
                kind = data.get("kind", "clips")
                if kind not in ("clips", "delogo", "enhance", "publish", "trends", "tool", "doctor", "selftest", "youtube",
                                "tiktok", "yt_login", "insights_profile", "insights_niches", "insights_plan"):
                    return self._err(400, "Type de travail inconnu.")
                return self._json({"id": start_job(kind, data.get("options", {}))})
            if m := re.fullmatch(r"/api/jobs/([\w-]+)/cancel", path):
                job = JOBS.get(m.group(1))
                if job and job.get("proc"):
                    job["cancel"] = True
                    job["proc"].terminate()
                return self._json({"ok": True})
            self._err(404, "Introuvable.")
        except ValueError as exc:
            self._err(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            self._err(500, f"Erreur interne : {exc}")

    def _local_only(self) -> bool:
        """Les connexions de comptes ne sont autorisées que depuis cet ordinateur (pas depuis le téléphone en mode --lan)."""
        return self.client_address[0] in ("127.0.0.1", "::1")

    def _serve_static(self, rel: str) -> None:
        target = (WEB / rel).resolve()
        if WEB.resolve() not in target.parents or not target.is_file():
            return self._err(404, "Introuvable.")
        body = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in (".js", ".css", ".html"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _tiktok_callback(self, q: dict) -> None:
        if not self._local_only():
            return self._err(403, "Connexion de compte : seulement depuis l'ordinateur.")
        try:
            if "error" in q:
                raise StudioError(f"TikTok a refusé l'autorisation : {q['error'][0]}")
            info = accounts.tiktok_complete(self.path.split("?", 1)[1] if "?" in self.path else "")
            msg = f"Compte TikTok connecté{' : ' + info['nickname'] if info.get('nickname') else ''}. Tu peux fermer cet onglet et revenir à Phenix-video."
            ok = True
        except StudioError as exc:
            msg, ok = str(exc), False
        page = (f'<!doctype html><meta charset="utf-8"><title>Phenix-video</title><body style="font:18px system-ui;background:#0e1016;'
                f'color:#eee;display:grid;place-items:center;min-height:100vh;margin:0"><div style="max-width:520px;padding:24px;text-align:center">'
                f'<h2 style="color:{"#7ee787" if ok else "#ff7b72"}">{"Connexion réussie" if ok else "Connexion impossible"}</h2><p>{html.escape(msg)}</p></div>').encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def _accounts_post(self, action: str, data: dict) -> None:
        if not self._local_only():
            return self._err(403, "Connexion de compte : seulement depuis l'ordinateur.")
        try:
            if action == "youtube/logout":
                import youtube_upload
                youtube_upload.logout()
            elif action == "tiktok/config":
                accounts.tiktok_save_app(str(data.get("client_key", "")), str(data.get("client_secret", "")),
                                         str(data.get("redirect_uri", "")))
            elif action == "tiktok/connect":
                modes = [m for m in data.get("modes", ["upload"]) if m in ("upload", "publish")] or ["upload"]
                url = accounts.tiktok_auth_url(modes)
                threading.Timer(0.2, lambda: webbrowser.open(url)).start()
                return self._json({"ok": True, "url": url})
            elif action == "tiktok/complete":
                return self._json({"ok": True, **accounts.tiktok_complete(str(data.get("value", "")))})
            elif action == "tiktok/logout":
                accounts.tiktok_logout()
            else:
                return self._err(404, "Introuvable.")
            self._json({"ok": True})
        except StudioError as exc:
            self._err(400, str(exc))

    def _upload(self, name: str):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return self._err(400, "Fichier vide.")
        if n > MAX_UPLOAD:
            return self._err(413, "Fichier trop gros (8 Go max).")
        d = WORKDIR / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        final = f"{uuid.uuid4().hex[:6]}_{safe_name(name)}"
        tmp = d / f".{final}.part"
        left = n
        with open(tmp, "wb") as fh:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    tmp.unlink(missing_ok=True)
                    return self._err(400, "Téléversement interrompu.")
                fh.write(chunk)
                left -= len(chunk)
        tmp.replace(d / final)
        self._json({"id": final, "size": n})

    def _serve_file(self, base: Path, rel: str, download: bool):
        target = (base / rel).resolve()
        if base.resolve() not in target.parents or not target.is_file():
            return self._err(404, "Fichier introuvable.")
        size = target.stat().st_size
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng and (m := re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())):
            a, b = m.groups()
            if a:
                start = int(a)
                end = int(b) if b else size - 1
            elif b:
                start = max(0, size - int(b))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            end = min(end, size - 1)
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
        self.end_headers()
        try:
            with open(target, "rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main() -> None:
    global WORKDIR
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--workdir", default=str(WORKDIR), help="dossier des fichiers envoyés et des résultats")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--lan", action="store_true", help="accès depuis un téléphone du même Wi-Fi (protégé par un code PIN)")
    ap.add_argument("--pin", default=None, help="avec --lan : code à utiliser (sinon 6 chiffres au hasard)")
    args = ap.parse_args()
    global LAN, PIN
    WORKDIR = Path(args.workdir).expanduser().resolve()
    if args.lan:
        LAN = True
        PIN = args.pin or f"{secrets.randbelow(10 ** 6):06d}"
        if len(PIN) < 4:
            sys.exit("[erreur] --pin : 4 caractères minimum.")
    (WORKDIR / "jobs").mkdir(parents=True, exist_ok=True)
    (WORKDIR / "uploads").mkdir(parents=True, exist_ok=True)
    srv, port = None, args.port
    for candidate in range(args.port, args.port + 20):  # port occupé (appli déjà lancée ?) : on prend le suivant
        try:
            srv = ThreadingHTTPServer(("0.0.0.0" if LAN else "127.0.0.1", candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if srv is None:
        sys.exit(f"[erreur] aucun port libre entre {args.port} et {args.port + 19}. Essaie --port 9000.")
    if port != args.port:
        print(f"[info] port {args.port} occupé (l'application tourne peut-être déjà) : utilisation du port {port}.")
    url = f"http://127.0.0.1:{port}"
    print(f"Phenix-video : {url}\nDossier de travail : {WORKDIR}\nCtrl+C pour arrêter.")
    if LAN:
        print(f"\nTéléphone (même Wi-Fi) : http://{local_ip()}:{port}\nCode PIN : {PIN}\n"
              "Ce mode n'est pas chiffré (HTTP) : à utiliser seulement sur un réseau de confiance.")
    if not args.no_browser and not LAN:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == "__main__":
    main()

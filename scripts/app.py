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
MAX_UPLOAD = 8 * 1024 ** 3  # 8 Go
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
# Mode réseau local (--lan) : accès depuis un téléphone du même Wi-Fi, protégé par un code PIN.
LAN = False
PIN = ""
TOKENS: set[str] = set()
FAILS: dict[str, tuple[int, float]] = {}  # ip -> (échecs, bloqué jusqu'à)

MANIFEST = json.dumps({"name": "Phenix-video", "short_name": "Phenix", "start_url": "/", "display": "standalone",
                       "background_color": "#0f1115", "theme_color": "#f5b301",
                       "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}]})
ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="22" fill="#0f1115"/>'
        '<polygon points="22,48 20,14 40,30" fill="#f5b301"/><polygon points="78,48 80,14 60,30" fill="#f5b301"/>'
        '<ellipse cx="50" cy="52" rx="28" ry="26" fill="#2e2622" stroke="#f5b301" stroke-width="3"/>'
        '<polygon points="38,56 62,56 56,74 44,74" fill="#f0e1cd"/><polygon points="45,56 55,56 50,63" fill="#181212"/>'
        '<circle cx="39" cy="44" r="6" fill="#fff"/><circle cx="61" cy="44" r="6" fill="#fff"/>'
        '<circle cx="40" cy="45" r="3" fill="#181212"/><circle cx="62" cy="45" r="3" fill="#181212"/></svg>')
SW = "self.addEventListener('fetch',()=>{});"  # service worker minimal : rend l'application installable
LOGIN = ('<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         '<title>Phenix-video</title><link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#f5b301">'
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
        if p.suffix.lower() in (".mp4", ".jpg", ".md", ".json", ".txt") and ".tight" not in p.name and p.name != "log.txt" \
                and p.name not in ("options.json",):
            if p.suffix == ".json" and p.name not in ("clips.json", "report.json", "trends.json"):
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
    return {"id": job_id, "status": status, "log": log, "outputs": list_outputs(job_id), "clips": clips,
            "kind": (job or {}).get("kind", "")}


def history() -> list[dict]:
    root = WORKDIR / "jobs"
    out = []
    if root.is_dir():
        for d in sorted(root.iterdir(), reverse=True)[:30]:
            if d.is_dir():
                j = JOBS.get(d.name)
                out.append({"id": d.name, "status": j["status"] if j else "done"})
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
        files = {"/manifest.webmanifest": ("application/manifest+json", MANIFEST), "/icon.svg": ("image/svg+xml", ICON),
                 "/sw.js": ("application/javascript", SW)}
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
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/history":
            self._json(history())
        elif path == "/api/health":
            self._json({"ffmpeg": bool(shutil.which("ffmpeg")), "workdir": str(WORKDIR), "python": sys.version.split()[0]})
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
            if path == "/api/upload":
                return self._upload(parse_qs(url.query).get("name", ["video"])[0])
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}")
            if path == "/api/jobs":
                kind = data.get("kind", "clips")
                if kind not in ("clips", "delogo", "enhance", "publish", "trends"):
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


PAGE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phenix-video</title>
<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#f5b301">
<style>
:root{--bg:#0f1115;--card:#181b22;--line:#2a2f3a;--tx:#e8eaf0;--mut:#8b93a7;--ac:#f5b301;--ok:#3ecf8e;--er:#ff5d5d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
header{padding:18px 20px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
h1{font-size:18px;margin:0}header small{color:var(--mut)}
main{max-width:1100px;margin:0 auto;padding:16px;display:grid;gap:16px;grid-template-columns:minmax(0,380px) minmax(0,1fr)}
@media(max-width:860px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
h2{font-size:14px;margin:0 0 12px;color:var(--ac);text-transform:uppercase;letter-spacing:.06em}
label{display:block;font-size:13px;color:var(--mut);margin:10px 0 4px}
input,select,textarea{width:100%;background:#0f1218;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:9px;font:inherit}
input[type=checkbox]{width:auto;margin-right:8px}.chk{display:flex;align-items:center;margin:8px 0;color:var(--tx);font-size:14px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
button{background:var(--ac);color:#111;border:0;border-radius:8px;padding:11px 14px;font-weight:700;cursor:pointer;width:100%;margin-top:14px;font:inherit;font-weight:700}
button.sec{background:transparent;color:var(--tx);border:1px solid var(--line)}button:disabled{opacity:.5;cursor:not-allowed}
.drop{border:2px dashed var(--line);border-radius:10px;padding:16px;text-align:center;color:var(--mut);cursor:pointer}
.drop.on{border-color:var(--ac);color:var(--tx)}
pre{background:#0b0d11;border:1px solid var(--line);border-radius:8px;padding:10px;max-height:240px;overflow:auto;font-size:12px;white-space:pre-wrap;margin:10px 0 0}
.st{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;background:#22262f}
.st.done{color:var(--ok)}.st.error{color:var(--er)}.st.running{color:var(--ac)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px;margin-top:12px}
.v{background:#0f1218;border:1px solid var(--line);border-radius:10px;padding:8px}
.v video{width:100%;aspect-ratio:9/16;object-fit:contain;background:#000;border-radius:6px}
.v a{color:var(--ac);font-size:12px;word-break:break-all}.note{font-size:12px;color:var(--mut);margin-top:10px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.tabs{display:flex;gap:8px;margin-bottom:10px}.tabs button{margin:0;padding:8px}.hide{display:none}
.bar{height:6px;background:#0f1218;border-radius:4px;overflow:hidden;margin-top:8px}.bar i{display:block;height:100%;background:var(--ac);width:0}
</style></head><body>
<header><h1>Phenix-video</h1><small>100 % local · gratuit · rien n'est envoyé sur Internet</small>
<small id="health"></small></header>
<main>
<section class="card">
  <div class="tabs"><button class="sec" id="t1">Clips &amp; doublage</button><button class="sec" id="t2">Masquer ma marque</button><button class="sec" id="t3">Améliorer</button><button class="sec" id="t4">Tendances</button></div>
  <div id="srcbox">

  <h2>1. Vidéo</h2>
  <div class="drop" id="drop">Glisse ta vidéo ici ou clique pour choisir<input id="file" type="file" accept="video/*" hidden></div>
  <div class="bar"><i id="up"></i></div>
  <label>…ou un lien (ta propre vidéo, ou avec autorisation)</label>
  <input id="url" placeholder="https://www.youtube.com/watch?v=…">
  <div class="note" id="src">Aucune source.</div></div>

  <div id="p1">
  <h2 style="margin-top:18px">2. Montage</h2>
  <div class="row"><div><label>Nombre de clips</label><input id="clips" type="number" value="5" min="1" max="20"></div>
  <div><label>Format</label><select id="aspect"><option>9:16</option><option>16:9</option><option>1:1</option><option>4:5</option></select></div></div>
  <div class="row"><div><label>Durée min (s)</label><input id="min" type="number" value="75"></div>
  <div><label>Durée max (s)</label><input id="max" type="number" value="180"></div></div>
  <div class="chk"><input id="short" type="checkbox">Clips courts (20–60 s)</div>
  <div class="chk"><input id="tighten" type="checkbox" checked>Couper les blancs (rythme dynamique)</div>
  <div class="row"><div><label>Sous-titres</label><select id="style"><option value="pop">Pop (mot jaune)</option><option value="karaoke">Karaoké</option><option value="clean">Bandeau</option><option value="minimal">Minimal</option></select></div>
  <div><label>Qualité</label><select id="quality"><option value="balanced">Équilibrée</option><option value="high">Haute</option><option value="max">Maximale</option><option value="fast">Rapide</option></select></div></div>

  <h2 style="margin-top:18px">3. Langue &amp; voix</h2>
  <label>Traduire vers</label>
  <select id="to"><option value="">Garder la langue d'origine</option><option value="fr">Français</option><option value="en">Anglais</option><option value="es">Espagnol</option><option value="pt">Portugais</option><option value="de">Allemand</option><option value="ar">Arabe</option></select>
  <div class="chk"><input id="dub" type="checkbox" checked>Remplacer la voix (voix off de synthèse)</div>
  <div class="row"><div><label>Voix</label><select id="voice"><option value="female">Féminine</option><option value="male">Masculine</option><option value="both">Les deux (2 versions)</option></select></div>
  <div><label>Son d'origine</label><select id="bg"><option value="duck">Baissé</option><option value="none">Supprimé</option><option value="keep">Gardé</option></select></div></div>
  <button id="go">Lancer</button>
  <button class="sec" id="an">Analyser seulement (voir les moments choisis)</button>
  </div>

  <div id="p2" class="hide">
    <h2 style="margin-top:18px">2. Zones de TA marque</h2>
    <div class="chk"><input class="ar" type="checkbox" value="tl">Haut gauche</div>
    <div class="chk"><input class="ar" type="checkbox" value="tr">Haut droite</div>
    <div class="chk"><input class="ar" type="checkbox" value="bl">Bas gauche</div>
    <div class="chk"><input class="ar" type="checkbox" value="br" checked>Bas droite</div>
    <label>Méthode</label><select id="method"><option value="blur">Flou</option><option value="delogo">Effacement doux</option><option value="box">Bandeau noir</option></select>
    <button id="godl">Masquer</button>
    <div class="note">À utiliser pour ton propre logo ou nom de compte. Ne retire pas le crédit d'un autre créateur : c'est contraire aux règles des plateformes et à son droit d'auteur.</div>
  </div>
  <div id="p4" class="hide">
    <h2 style="margin-top:18px">Analyser des vidéos virales</h2>
    <div class="note">Colle des liens (un par ligne) de vidéos qui marchent dans ta niche (TikTok, YouTube, Instagram…). Phenix-video lit les infos publiques (titre, durée, vues, hashtags) et en tire la formule : durée, formes d'accroche, hashtags, idées de titres pour TON sujet. Il ne copie pas les vidéos.</div>
    <label>Liens</label><textarea id="tr_links" rows="5" placeholder="https://www.tiktok.com/@…/video/…&#10;https://www.youtube.com/shorts/…"></textarea>
    <label>…ou recherche YouTube (si aucun lien)</label><input id="tr_search" placeholder="astuces argent">
    <div class="row"><div><label>Ton sujet</label><input id="tr_theme" placeholder="ex. l'argent, le football, la cuisine"></div>
    <div><label>Langue des idées</label><select id="tr_lang"><option value="fr">Français</option><option value="en">Anglais</option></select></div></div>
    <label>Traduire les titres proposés vers</label>
    <select id="tr_to"><option value="">Non</option><option value="fr">Français</option><option value="en">Anglais</option><option value="es">Espagnol</option><option value="pt">Portugais</option><option value="de">Allemand</option><option value="ar">Arabe</option></select>
    <div class="chk"><input id="tr_deep" type="checkbox">Analyse approfondie (télécharge en basse définition : accroche parlée + rythme de montage, plus lent)</div>
    <button id="gotr">Analyser les tendances</button>
    <div class="note">Ce sont des corrélations, pas une recette garantie. Inspire-toi de la formule, refais ton propre contenu.</div>
    <pre id="trbox" class="hide" style="white-space:pre-wrap;max-height:480px;overflow:auto"></pre>
  </div>
  <div id="p3" class="hide">
    <h2 style="margin-top:18px">2. Améliorer la vidéo</h2>
    <div class="note" id="src3">Utilise « Améliorer ce clip » sous un clip produit, ou la vidéo choisie ci-dessus.</div>
    <div class="chk"><input id="e_clean" type="checkbox" checked>Nettoyer (bruit audio/vidéo, netteté, volume)</div>
    <label>Arrière-plan (personne face caméra)</label>
    <select id="e_bg"><option value="">Garder</option><option value="blur">Flou</option><option value="color">Couleur unie</option><option value="image">Image (à téléverser)</option></select>
    <div class="row"><div><label>Couleur</label><input id="e_col" type="color" value="#0b1f3a"></div>
    <div><label>Image de fond</label><input id="e_img" type="file" accept="image/*"></div></div>
    <label>Effets (plusieurs possibles)</label>
    <div id="fxlist" class="row"></div>
    <label>Titre animé (3 s)</label><input id="e_title" maxlength="80" placeholder="Optionnel">
    <div class="chk"><input id="e_mascot" type="checkbox">Mascotte ANUBIS (bouche synchronisée à la voix)</div>
    <div class="row"><div><label>Position mascotte</label><select id="e_mpos"><option value="br">Bas droite</option><option value="bl">Bas gauche</option><option value="tr">Haut droite</option><option value="tl">Haut gauche</option></select></div>
    <div><label>Sticker / GIF (à toi)</label><input id="e_stk" type="file" accept="image/*"></div></div>
    <button id="goenh">Améliorer</button>
    <div class="note">Personnages : seulement ta mascotte, la mascotte fournie ou tes propres images (pas de personnages protégés).</div>
  </div>
</section>

<section>
  <div class="card"><h2>Résultat</h2>
    <div id="status" class="note">Rien en cours.</div>
    <pre id="log" class="hide"></pre>
    <button class="sec hide" id="cancel" style="width:auto">Annuler</button>
    <div id="clipsbox" class="hide"></div>
    <div class="grid" id="out"></div>
    <button class="sec hide" id="pub" style="width:auto">Préparer le dossier de publication (YouTube / TikTok)</button>
    <div id="pubbox" class="note"></div>
    <div class="note hide" id="ai">⚠ Voix de synthèse : active l'étiquette « contenu généré par IA » à la publication. Vérifie tes droits et relis la traduction.</div>
  </div>
  <div class="card" style="margin-top:16px"><h2>Historique</h2><div id="hist" class="note"></div></div>
</section>
</main>
<footer style="text-align:center;color:var(--mut);font-size:12px;padding:18px">Phenix-video · © 2026 Phenix - kcw</footer>
<script>
const $=id=>document.getElementById(id);let source="",cur=null,timer=null,kind="clips";
const enc=p=>String(p).split('/').map(encodeURIComponent).join('/');
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
fetch('/api/health').then(r=>r.json()).then(h=>{$('health').textContent=(h.ffmpeg?'FFmpeg ✓':'⚠ FFmpeg introuvable')+' · dossier : '+h.workdir});
function tab(n){kind=['','clips','delogo','enhance','trends'][n];['p1','p2','p3','p4'].forEach((id,i)=>$(id).classList.toggle('hide',n!=i+1));$('srcbox').classList.toggle('hide',n==4)}
$('t1').onclick=()=>tab(1);$('t2').onclick=()=>tab(2);$('t3').onclick=()=>tab(3);$('t4').onclick=()=>tab(4);
const FX={vignette:'Vignette',warm:'Chaud',cool:'Froid',cinema:'Cinéma',vivid:'Éclatant',bw:'Noir & blanc',grain:'Grain',sharpen:'Netteté',glitch:'Glitch',shake:'Tremblement',flash:'Flash',zoomin:'Zoom lent',fade:'Fondu',lowlight:'Éclaircir'};
$('fxlist').innerHTML=Object.entries(FX).map(([k,v])=>'<label class="chk" style="margin:2px 0"><input type="checkbox" class="fxc" value="'+k+'">'+v+'</label>').join('');
let enhSrc="";
function upfile(inp,cb){const f=inp.files[0];if(!f)return;const x=new XMLHttpRequest();x.open('POST','/api/upload?name='+encodeURIComponent(f.name));x.onload=()=>{try{cb(JSON.parse(x.responseText).id)}catch(e){alert('Échec envoi')}};x.send(f)}
let bgImg="",stkImg="";$('e_img').onchange=()=>upfile($('e_img'),i=>bgImg=i);$('e_stk').onchange=()=>upfile($('e_stk'),i=>stkImg=i);
$('goenh').onclick=()=>{const o={source:enhSrc||$('url').value.trim()||source,clean:$('e_clean').checked,bg:$('e_bg').value,bg_color:$('e_col').value,bg_image:bgImg,
 effects:[...document.querySelectorAll('.fxc:checked')].map(x=>x.value),title:$('e_title').value,mascot:$('e_mascot').checked,mascot_pos:$('e_mpos').value,sticker:stkImg,quality:'balanced'};
 if(o.bg==='image'&&!bgImg){alert("Choisis l'image de fond.");return}start('enhance',o)};
$('pub').onclick=async()=>{const r=await fetch('/api/jobs',{method:'POST',body:JSON.stringify({kind:'publish',options:{job:cur}})});const j=await r.json();
 if(j.error){alert(j.error);return}$('pubbox').textContent='Préparation…';const t=setInterval(async()=>{const v=await (await fetch('/api/jobs/'+j.id)).json();
  if(v.status==='done'){clearInterval(t);poll();$('pubbox').textContent='Dossier prêt : voir les fichiers texte listés ci-dessous (titre, description, hashtags). Dossier : '+'jobs/'+cur+'/out/publish'}
  else if(v.status==='error'){clearInterval(t);$('pubbox').textContent='Échec : '+v.log.slice(-300)}},1500)};
$('drop').onclick=()=>$('file').click();
['dragover','dragenter'].forEach(e=>$('drop').addEventListener(e,ev=>{ev.preventDefault();$('drop').classList.add('on')}));
['dragleave','drop'].forEach(e=>$('drop').addEventListener(e,ev=>{ev.preventDefault();$('drop').classList.remove('on')}));
$('drop').addEventListener('drop',ev=>{if(ev.dataTransfer.files[0])upload(ev.dataTransfer.files[0])});
$('file').onchange=e=>{if(e.target.files[0])upload(e.target.files[0])};
function upload(f){$('src').textContent='Envoi de '+f.name+'…';const x=new XMLHttpRequest();
 x.open('POST','/api/upload?name='+encodeURIComponent(f.name));
 x.upload.onprogress=e=>{if(e.lengthComputable)$('up').style.width=(100*e.loaded/e.total)+'%'};
 x.onload=()=>{try{const r=JSON.parse(x.responseText);if(r.id){source=r.id;$('url').value='';$('src').textContent='Prêt : '+f.name+' ('+(f.size/1048576).toFixed(1)+' Mo)'}else $('src').textContent=r.error||'Échec'}catch(e){$('src').textContent='Échec'}};
 x.onerror=()=>$('src').textContent='Échec de l\'envoi';x.send(f)}
function opts(analyse){const o={source:$('url').value.trim()||source,analyse_only:analyse,clips:$('clips').value,aspect:$('aspect').value,
 min:$('min').value,max:$('max').value,short:$('short').checked,tighten:$('tighten').checked,style:$('style').value,quality:$('quality').value,
 translate_to:$('to').value,dub:$('dub').checked,voice:$('voice').value,bg:$('bg').value};return o}
async function start(k,o){if(!o.source){alert('Ajoute une vidéo ou un lien.');return}
 const r=await fetch('/api/jobs',{method:'POST',body:JSON.stringify({kind:k,options:o})});const j=await r.json();
 if(j.error){alert(j.error);return}cur=j.id;$('log').classList.remove('hide');$('cancel').classList.remove('hide');poll()}
$('go').onclick=()=>start('clips',opts(false));$('an').onclick=()=>start('clips',opts(true));
$('godl').onclick=()=>start('delogo',{source:$('url').value.trim()||source,method:$('method').value,areas:[...document.querySelectorAll('.ar:checked')].map(x=>x.value)});
$('gotr').onclick=async()=>{const o={links:$('tr_links').value,search:$('tr_search').value,theme:$('tr_theme').value,lang:$('tr_lang').value,translate_to:$('tr_to').value,deep:$('tr_deep').checked};
 if(!o.links.trim()&&!o.search.trim()){alert('Colle des liens ou écris une recherche.');return}
 const r=await fetch('/api/jobs',{method:'POST',body:JSON.stringify({kind:'trends',options:o})});const j=await r.json();
 if(j.error){alert(j.error);return}cur=j.id;$('trbox').classList.add('hide');$('log').classList.remove('hide');$('cancel').classList.remove('hide');poll()};
$('cancel').onclick=()=>fetch('/api/jobs/'+cur+'/cancel',{method:'POST',body:'{}'});
function poll(){clearTimeout(timer);if(!cur)return;fetch('/api/jobs/'+cur).then(r=>r.json()).then(v=>{render(v);if(v.status==='running'||v.status==='queued')timer=setTimeout(poll,1500);else hist()})}
function render(v){const lab={queued:'En attente',running:'En cours…',done:'Terminé',error:'Erreur',cancelled:'Annulé'}[v.status]||v.status;
 const errl=(v.log.split('\n').filter(x=>x.startsWith('[erreur]')).pop()||'');
 $('status').innerHTML='<span class="st '+v.status+'">'+lab+'</span> '+esc(v.id)+(v.status==='error'&&errl?'<br><b style="color:var(--er)">'+esc(errl)+'</b>':'');const l=$('log');l.textContent=v.log;l.scrollTop=l.scrollHeight;
 if(v.status!=='running'&&v.status!=='queued')$('cancel').classList.add('hide');
 const mp=v.outputs.filter(o=>o.type==='mp4'),oth=v.outputs.filter(o=>o.type!=='mp4'&&o.type!=='jpg');
 $('out').innerHTML=mp.map(o=>'<div class="v"><video controls preload="metadata" src="/files/'+v.id+'/'+enc(o.path)+'"></video><div class="note">'+esc(o.name)+' · '+(o.size/1048576).toFixed(1)+' Mo</div><a href="/files/'+v.id+'/'+enc(o.path)+'?dl=1">Télécharger</a>'+(v.kind==='clips'?' · <a href="#" class="enh" data-s="job:'+v.id+'/'+enc(o.path)+'">Améliorer ce clip</a>':'')+'</div>').join('')
 +oth.map(o=>'<div class="v"><a href="/files/'+v.id+'/'+enc(o.path)+'" target="_blank">'+esc(o.name)+'</a></div>').join('');
 $('pub').classList.toggle('hide',!(v.status==='done'&&v.kind==='clips'&&mp.length));
 $('ai').classList.toggle('hide',!(mp.length&&v.kind==='clips'&&$('dub').checked&&$('to').value));
 if(v.kind==='trends'&&v.status==='done'){const f=v.outputs.find(o=>o.name==='TENDANCES.md'),g=v.outputs.find(o=>o.name==='idees.md');
  if(f)Promise.all([fetch('/files/'+v.id+'/'+enc(f.path)).then(r=>r.text()),g?fetch('/files/'+v.id+'/'+enc(g.path)).then(r=>r.text()):''] ).then(([x,y])=>{const b=$('trbox');b.textContent=x+'\n\n'+y;b.classList.remove('hide')})}
 document.querySelectorAll('a.enh').forEach(a=>a.onclick=e=>{e.preventDefault();enhSrc=a.dataset.s.split('/').map(decodeURIComponent).join('/');$('src3').textContent='Clip choisi : '+enhSrc.split('/').pop();tab(3)});
 const cb=$('clipsbox');if(v.clips&&v.clips.clips){cb.classList.remove('hide');
  cb.innerHTML='<table><tr><th>#</th><th>Début–fin</th><th>Titre / extrait</th></tr>'+v.clips.clips.map(c=>'<tr><td>'+esc(c.id??'')+'</td><td>'+Math.round(c.start)+'–'+Math.round(c.end)+' s</td><td><b>'+esc(c.title||'')+'</b><br>'+esc((c.text||'').slice(0,160))+'</td></tr>').join('')+'</table>'}}
function hist(){fetch('/api/history').then(r=>r.json()).then(h=>{$('hist').innerHTML=h.length?h.map(x=>'<a href="#" data-id="'+x.id+'" style="color:var(--ac)">'+x.id+'</a> · '+x.status).join('<br>'):'Aucun travail.';
 document.querySelectorAll('#hist a').forEach(a=>a.onclick=e=>{e.preventDefault();cur=a.dataset.id;$('log').classList.remove('hide');poll()})})}
hist();
if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js").catch(()=>{});
</script></body></html>
"""


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

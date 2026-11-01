#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Application PC : ouvre Phenix-video dans sa propre fenêtre (comme un logiciel), 100 % local.

  desktop.py [--workdir DOSSIER] [--port 8765] [--lan] [--browser]

Ordre d'essai pour la fenêtre :
  1. fenêtre native (pywebview : WebView2 sous Windows, GTK/Qt sous Linux) si le module est installé ;
  2. « mode application » de Microsoft Edge / Google Chrome / Chromium (fenêtre sans barre d'adresse, aucun module à installer) ;
  3. navigateur par défaut (--browser force ce choix).
Fermer la fenêtre arrête le serveur local et les traitements en cours.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ICON = ROOT / "assets" / "icon.png"
TITLE = "Phenix-video"


def free_port(start: int) -> int:
    for p in range(start, start + 40):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise SystemExit("[erreur] aucun port libre entre %d et %d" % (start, start + 39))


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def chromium_app() -> str | None:
    cands: list[str] = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands += [rf"{base}\Microsoft\Edge\Application\msedge.exe", rf"{base}\Google\Chrome\Application\chrome.exe"]
    elif sys.platform == "darwin":
        cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    for name in ("microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "chrome", "msedge"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    return next((c for c in cands if c and Path(c).is_file()), None)


def open_window(url: str, workdir: Path, force_browser: bool) -> bool:
    """Retourne True si une fenêtre dédiée a été utilisée et fermée (False : navigateur ordinaire)."""
    if not force_browser:
        try:
            import webview  # type: ignore
            try:
                webview.settings["ALLOW_DOWNLOADS"] = True
            except Exception:  # noqa: BLE001
                pass
            webview.create_window(TITLE, url, width=1320, height=880, min_size=(900, 640))
            webview.start(icon=str(ICON) if ICON.is_file() else None)
            return True
        except Exception as exc:  # noqa: BLE001 - module absent ou moteur web manquant
            print(f"[fenêtre] mode natif indisponible ({type(exc).__name__}) : essai du mode application…", file=sys.stderr)
        exe = chromium_app()
        if exe:
            profile = workdir / ".appprofile"
            profile.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run([exe, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1320,880",
                                "--no-first-run", "--no-default-browser-check"], check=False)
                return True
            except OSError as exc:
                print(f"[fenêtre] échec du mode application : {exc}", file=sys.stderr)
    webbrowser.open(url)
    return False


def install_linux_entry() -> None:
    """Entrée de menu « Phenix-video » (Linux / WSLg) : lanceur .desktop + icône dans ~/.local/share."""
    apps = Path.home() / ".local" / "share" / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    entry = apps / "phenix-video.desktop"
    entry.write_text(
        "[Desktop Entry]\nType=Application\nName=Phenix-video\nComment=Studio vidéo local : clips, doublage, sous-titres\n"
        f"Exec={py} {HERE / 'desktop.py'}\nIcon={ICON}\nTerminal=false\nCategories=AudioVideo;Video;\n", encoding="utf-8")
    entry.chmod(0o755)
    print(f"Entrée de menu créée : {entry}")
    desk = Path.home() / "Desktop"
    if desk.is_dir():
        shutil.copy2(entry, desk / "Phenix-video.desktop")
        print(f"Raccourci sur le Bureau : {desk / 'Phenix-video.desktop'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", default=str(Path.home() / "PhenixVideo"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lan", action="store_true", help="autorise aussi le téléphone (code PIN affiché dans le terminal)")
    ap.add_argument("--browser", action="store_true", help="navigateur par défaut au lieu d'une fenêtre dédiée")
    ap.add_argument("--install-shortcut", action="store_true", help="Linux : crée l'entrée de menu Phenix-video")
    a = ap.parse_args()
    if a.install_shortcut:
        return install_linux_entry()
    workdir = Path(a.workdir).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    # Déjà lancée ? on rouvre simplement une fenêtre sur le serveur existant.
    lock = workdir / ".desktop.json"
    server = None
    port = None
    if lock.is_file():
        try:
            port = int(json.loads(lock.read_text())["port"])
            if not healthy(port):
                port = None
        except (OSError, ValueError, KeyError):
            port = None
    if port is None:
        port = free_port(a.port)
        cmd = [sys.executable, str(HERE / "app.py"), "--port", str(port), "--no-browser", "--workdir", str(workdir)]
        if a.lan:
            cmd.append("--lan")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        log = open(workdir / "desktop.log", "w", encoding="utf-8")
        flags = 0x08000000 if sys.platform.startswith("win") else 0  # CREATE_NO_WINDOW
        server = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, creationflags=flags)
        for _ in range(100):
            if healthy(port) or server.poll() is not None:
                break
            time.sleep(0.2)
        if not healthy(port):
            tail = (workdir / "desktop.log").read_text(encoding="utf-8", errors="replace")[-600:]
            raise SystemExit(f"[erreur] le serveur local n'a pas démarré.\n{tail}")
        lock.write_text(json.dumps({"port": port, "pid": server.pid}))
    print(f"{TITLE} : http://127.0.0.1:{port}  (dossier : {workdir})", flush=True)
    used_window = False
    try:
        used_window = open_window(f"http://127.0.0.1:{port}", workdir, a.browser)
        if server and not used_window:
            print("Navigateur ouvert. Ctrl+C pour arrêter l'application.", flush=True)
            server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
            lock.unlink(missing_ok=True)
        print("Arrêt.", flush=True)


if __name__ == "__main__":
    main()

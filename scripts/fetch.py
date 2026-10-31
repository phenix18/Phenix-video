#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Récupère une vidéo depuis un lien (YouTube, TikTok, Instagram, X, Facebook, Vimeo, lien direct .mp4…).

Moteur : yt-dlp (libre, gratuit, pip install yt-dlp). Télécharge la meilleure qualité jusqu'à --max-height
(1080 par défaut), de préférence en H.264 pour une compatibilité maximale, et fusionne image + son en .mp4.

Droits : ne télécharge que des contenus dont tu détiens les droits ou que leur auteur autorise ;
les conditions d'utilisation des plateformes s'appliquent.

Exemples :
  fetch.py "https://www.youtube.com/watch?v=XXXX" -o downloads
  fetch.py "https://www.tiktok.com/@compte/video/123" -o downloads
  fetch.py URL -o downloads --max-height 2160          # 4K si disponible (recadrage 9:16 plus net)
  fetch.py URL -o downloads --cookies-from-browser chrome   # vidéos réservées à un compte / limitées par l'âge
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, die, need_binary, probe, save_json  # noqa: E402

RIGHTS_NOTE = ("[droits] Utilise uniquement des vidéos dont tu détiens les droits ou autorisées par leur auteur "
               "(conditions des plateformes).")


def is_url(text: str) -> bool:
    return bool(re.match(r"^https?://", text.strip(), re.I))


def build_format(max_height: int) -> str:
    h = int(max_height)
    return (f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/"   # H.264 + AAC : le plus compatible
            f"bv*[height<={h}]+ba/"                          # sinon n'importe quel codec
            f"b[height<={h}]/b")                             # flux unique (TikTok, liens directs)


def download(url: str, out_dir: str, max_height: int = 1080, cookies_from_browser: str | None = None,
             verbose: bool = True) -> dict:
    """Télécharge `url` dans `out_dir`. Retourne {"path", "title", "id", "uploader", "width", "height", "duration"}."""
    try:
        import yt_dlp
        from yt_dlp.utils import DownloadError
    except ImportError as exc:
        raise StudioError("yt-dlp n'est pas installé :  pip install yt-dlp") from exc
    need_binary("ffmpeg")  # nécessaire pour fusionner image et son
    if not is_url(url):
        raise StudioError(f"Ce n'est pas un lien http(s) : {url}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    last = {"pct": -1}

    def hook(d):
        if not verbose or d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        if total:
            pct = int(d["downloaded_bytes"] * 100 / total)
            if pct != last["pct"] and pct % 5 == 0:
                last["pct"] = pct
                print(f"\r[téléchargement] {pct:3d} %", end="", file=sys.stderr)

    opts = {
        "format": build_format(max_height),
        "merge_output_format": "mp4",
        "outtmpl": str(out / "%(title).80B [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [hook],
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if verbose:
        print(RIGHTS_NOTE, file=sys.stderr)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise StudioError("Aucune information récupérée pour ce lien.")
            if info.get("entries"):  # lien de playlist : on garde la première vidéo
                info = next(e for e in info["entries"] if e)
            done = (info.get("requested_downloads") or [{}])[0].get("filepath")
            path = Path(done) if done else Path(ydl.prepare_filename(info)).with_suffix(".mp4")
    except DownloadError as exc:
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).strip().splitlines()[-1]
        hint = ""
        low = msg.lower()
        if any(k in low for k in ("sign in", "age", "login", "private", "members")):
            hint = "\nVidéo privée ou limitée : essaie --cookies-from-browser chrome (ou firefox, edge)."
        elif any(k in low for k in ("unable to download", "urlopen", "timed out", "connection", "resolve", "403", "tunnel")):
            hint = "\nProblème réseau : vérifie la connexion (un réseau filtré peut bloquer la plateforme)."
        elif "unsupported url" in low:
            hint = "\nLien non pris en charge : ouvre la vidéo et copie son adresse directe."
        raise StudioError(f"Téléchargement impossible : {msg}{hint}") from exc
    if verbose:
        print(file=sys.stderr)
    if not path.exists():
        found = sorted(out.glob(f"*[[]{info.get('id', '')}[]].*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not found:
            raise StudioError("Le téléchargement s'est terminé mais le fichier est introuvable.")
        path = found[0]
    media = probe(path)
    meta = {"path": str(path), "title": info.get("title"), "id": info.get("id"), "uploader": info.get("uploader"),
            "width": media.width, "height": media.height, "fps": round(media.fps, 2),
            "duration": round(media.duration, 2), "url": url, "extractor": info.get("extractor_key")}
    save_json(path.with_suffix(".info.json"), meta)
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("-o", "--out", default="downloads", help="dossier de destination")
    ap.add_argument("--max-height", type=int, default=1080, help="hauteur max (720, 1080, 1440, 2160)")
    ap.add_argument("--cookies-from-browser", default=None, help="chrome|firefox|edge|safari…")
    args = ap.parse_args()
    try:
        meta = download(args.url, args.out, args.max_height, args.cookies_from_browser)
        print(f"[ok] {meta['path']}  ({meta['width']}x{meta['height']} @ {meta['fps']:g} fps, {meta['duration']:.0f}s)")
        if meta["height"] < 720 and meta["width"] < 720:
            print("[avertissement] Source en basse résolution : la sortie 1080p sera agrandie (moins nette).",
                  file=sys.stderr)
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()

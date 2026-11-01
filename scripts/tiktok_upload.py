#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Envoi d'une vidéo sur TON compte TikTok via l'API officielle « Content Posting » (gratuite, compte développeur requis).

  tiktok_upload.py --from-folder out/publish/01_mon-clip [--mode inbox|direct] [--privacy SELF_ONLY]
  tiktok_upload.py video.mp4 --caption "Légende #astuce" --mode inbox

Modes : inbox = brouillon à valider dans l'appli TikTok (recommandé au début) ; direct = publication (privée « moi seul » tant
que ton application n'a pas passé l'audit TikTok). Connexion : page Comptes de l'application (ou accounts.py). Voir accounts.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from accounts import tiktok_post_video  # noqa: E402
from common import StudioError, die  # noqa: E402


def caption_from_folder(f: Path) -> tuple[str, bool]:
    meta = json.loads((f / "metadata.json").read_text(encoding="utf-8")) if (f / "metadata.json").is_file() else {}
    cap = ""
    txt = f / "tiktok.txt"
    if txt.is_file():
        cap = txt.read_text(encoding="utf-8").split("\n\nRÉGLAGES")[0].strip()
    if not cap:
        cap = (meta.get("title", "") + " " + " ".join(meta.get("hashtags", []))).strip()
    return cap, bool(meta.get("synthetic_voice"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?")
    ap.add_argument("--from-folder")
    ap.add_argument("--caption", default="")
    ap.add_argument("--mode", choices=["inbox", "direct"], default="inbox")
    ap.add_argument("--privacy", default="SELF_ONLY", choices=["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"])
    ap.add_argument("--no-ai-label", action="store_true")
    a = ap.parse_args()
    try:
        video, cap, synth = a.video, a.caption, True
        if a.from_folder:
            f = Path(a.from_folder)
            if not (f / "video.mp4").is_file():
                raise StudioError(f"video.mp4 introuvable dans {f} (lance publish.py d'abord).")
            video = str(f / "video.mp4")
            c, synth = caption_from_folder(f)
            cap = cap or c
        if not video:
            ap.error("vidéo requise (ou --from-folder)")
        res = tiktok_post_video(video, cap, mode=a.mode, privacy=a.privacy, ai_label=synth and not a.no_ai_label,
                                log=lambda m: print(m, flush=True))
        end = {"SEND_TO_USER_INBOX": "Brouillon prêt : ouvre TikTok → notifications/boîte de réception pour le publier.",
               "PUBLISH_COMPLETE": "Publié.", "PROCESSING": "TikTok traite encore la vidéo : vérifie dans l'appli dans quelques minutes."}
        print(f"[ok] publish_id={res['publish_id']} — {end.get(res['status'], res['status'])}")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()

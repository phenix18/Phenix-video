#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Envoi d'une vidéo sur TON canal YouTube via l'API officielle (gratuite, quota ~6 envois/jour).

Prérequis (une seule fois, 10 minutes) :
  1. console.cloud.google.com → nouveau projet → activer « YouTube Data API v3 ».
  2. Écran de consentement OAuth (type Externe) → ajoute ton adresse comme utilisateur test.
  3. Identifiants → « ID client OAuth » type Application de bureau → télécharge client_secret.json.
  4. pip install google-api-python-client google-auth-oauthlib

  youtube_upload.py video.mp4 --title "Titre" --description-file youtube.txt --client-secret client_secret.json
  youtube_upload.py --from-folder out/publish/01_mon-clip --client-secret client_secret.json

Par défaut la vidéo est envoyée en PRIVÉ : tant que ton projet Google n'est pas validé (audit), l'API force le privé.
Tu la passes en public toi-même dans YouTube Studio après relecture. Non testé ici (réseau/compte Google nécessaires).
Le jeton est stocké dans ~/.cache/phenix-video/youtube_token.json (lecture réservée à ton compte).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import StudioError, die  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN = Path(os.environ.get("PHENIX_VIDEO_CACHE", Path.home() / ".cache" / "phenix-video")) / "youtube_token.json"


def _service(client_secret: str):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise StudioError("Installe : pip install google-api-python-client google-auth-oauthlib") from exc
    creds = None
    if TOKEN.is_file():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(client_secret).is_file():
                raise StudioError(f"client_secret.json introuvable : {client_secret} (voir l'aide du script).")
            flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)
        TOKEN.parent.mkdir(parents=True, exist_ok=True)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
        try:
            TOKEN.chmod(0o600)
        except OSError:
            pass
    return build("youtube", "v3", credentials=creds)


def upload(video: str, title: str, description: str, tags: list[str], *, privacy: str, synthetic: bool,
           client_secret: str, category: str = "22", language: str | None = None) -> str:
    if not Path(video).is_file():
        raise StudioError(f"Vidéo introuvable : {video}")
    yt = _service(client_secret)  # vérifie aussi que les bibliothèques Google sont installées
    from googleapiclient.http import MediaFileUpload
    body = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:15], "categoryId": category},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": synthetic},
    }
    if language:
        body["snippet"]["defaultAudioLanguage"] = language
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(video, chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  envoi {int(status.progress() * 100)} %")
    return resp["id"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?")
    ap.add_argument("--from-folder", help="dossier produit par publish.py (video.mp4 + metadata.json)")
    ap.add_argument("--title")
    ap.add_argument("--description", default="")
    ap.add_argument("--description-file")
    ap.add_argument("--tags", default="", help="mots séparés par des virgules")
    ap.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    ap.add_argument("--no-ai-label", action="store_true", help="NE PAS déclarer de contenu synthétique (déconseillé si voix IA)")
    ap.add_argument("--client-secret", default="client_secret.json")
    ap.add_argument("--lang", default=None)
    a = ap.parse_args()
    try:
        video, title, desc, tags, synth = a.video, a.title, a.description, [t for t in a.tags.split(",") if t], not a.no_ai_label
        if a.from_folder:
            f = Path(a.from_folder)
            if not (f / "metadata.json").is_file():
                raise StudioError(f"metadata.json introuvable dans {f} (lance publish.py d'abord).")
            meta = json.loads((f / "metadata.json").read_text(encoding="utf-8"))
            video = str(f / "video.mp4")
            title = title or meta["title"]
            desc = desc or meta["description"]
            tags = tags or [h.lstrip("#") for h in meta.get("hashtags", [])]
            synth = bool(meta.get("synthetic_voice")) and not a.no_ai_label
        if a.description_file:
            desc = Path(a.description_file).read_text(encoding="utf-8")
        if not video or not title:
            ap.error("vidéo et --title requis (ou --from-folder)")
        vid = upload(video, title, desc, tags, privacy=a.privacy, synthetic=synth, client_secret=a.client_secret,
                     language=a.lang)
        print(f"[ok] https://youtu.be/{vid}  (statut : {a.privacy}) — vérifie-la dans YouTube Studio avant de la rendre publique.")
    except StudioError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()

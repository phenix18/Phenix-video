#!/usr/bin/env python3
# Phenix-video — © 2026 Phenix - kcw. Tous droits réservés (voir LICENSE).
"""Connexions aux comptes (API officielles gratuites) : état YouTube + TikTok, OAuth TikTok (PKCE), envoi vidéo TikTok.

TikTok : « Content Posting API » (https://developers.tiktok.com). Il faut créer une application dans le portail développeur
(gratuit), y ajouter le produit « Login Kit » + « Content Posting API », déclarer l'adresse de retour (redirect URI) et copier
client_key / client_secret dans Phenix-video (page Comptes). Deux modes d'envoi :
  - « brouillon » (scope video.upload) : la vidéo arrive dans la boîte de réception de ton appli TikTok, tu la valides ;
  - « publication directe » (scope video.publish) : tant que ton application n'a pas passé l'audit TikTok, la vidéo ne peut
    être publiée qu'en « moi seul » (privé). L'audit se demande dans le portail (délai de plusieurs jours à semaines).
Jetons stockés dans ~/.cache/phenix-video (lecture réservée à ton compte). Non testé ici contre le vrai serveur TikTok (compte
développeur requis) : le flux est testé contre un serveur factice qui imite l'API.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from common import StudioError
except ImportError:  # exécuté hors du dossier scripts
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from common import StudioError

CACHE = Path(os.environ.get("PHENIX_VIDEO_CACHE", Path.home() / ".cache" / "phenix-video"))
YT_TOKEN = CACHE / "youtube_token.json"
YT_PROFILE = CACHE / "youtube_profile.json"
TT_APP = CACHE / "tiktok_app.json"
TT_TOKEN = CACHE / "tiktok_token.json"
API = os.environ.get("PHENIX_TIKTOK_API", "https://open.tiktokapis.com").rstrip("/")
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
_PENDING: dict[str, dict] = {}  # state -> {verifier, scope, time}

TT_ERRORS = {
    "unaudited_client_can_only_post_to_private_accounts": "Ton application TikTok n'est pas encore auditée : la publication directe "
        "n'est possible qu'en « moi seul ». Utilise le mode brouillon, ou demande l'audit dans le portail développeur.",
    "reached_active_user_cap": "Limite d'utilisateurs atteinte pour une application non auditée (5 par 24 h).",
    "privacy_level_option_mismatch": "Ce niveau de confidentialité n'est pas proposé pour ce compte.",
    "access_token_invalid": "Connexion TikTok expirée : reconnecte le compte (page Comptes).",
    "scope_not_authorized": "Autorisation manquante : reconnecte TikTok en cochant le mode d'envoi voulu.",
    "spam_risk_too_many_posts": "TikTok limite le nombre de publications par jour pour ce compte : réessaie plus tard.",
    "url_ownership_unverified": "Domaine non vérifié dans le portail TikTok.",
}


def _write_private(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _http(method: str, url: str, *, headers: dict | None = None, data: bytes | None = None, timeout: float = 60) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        raw, code = e.read(), e.code
    except (urllib.error.URLError, OSError) as e:
        raise StudioError(f"Réseau indisponible ({getattr(e, 'reason', e)}) : vérifie ta connexion.") from e
    try:
        return code, json.loads(raw or b"{}")
    except ValueError:
        return code, {"raw": raw[:300].decode("utf-8", "replace")}


def _tt_error(body: dict) -> str:
    err = (body.get("error") or {}) if isinstance(body.get("error"), dict) else {}
    code = err.get("code") or body.get("error") or ""
    msg = TT_ERRORS.get(str(code))
    if msg:
        return msg
    return f"TikTok a refusé la demande : {code or 'erreur inconnue'} {err.get('message', '') or body.get('error_description', '')}".strip()


# --------------------------------------------------------------------------- état
def status() -> dict:
    yt = {"connected": YT_TOKEN.is_file(), "profile": _read(YT_PROFILE) or None}
    app, tok = _read(TT_APP), _read(TT_TOKEN)
    now = time.time()
    tt = {"app_configured": bool(app.get("client_key") and app.get("client_secret")), "client_key": app.get("client_key", ""),
          "redirect_uri": app.get("redirect_uri", ""), "connected": bool(tok.get("access_token")),
          "nickname": tok.get("nickname"), "scope": tok.get("scope"),
          "refresh_valid": bool(tok.get("refresh_expires_at", 0) > now) if tok else False}
    return {"youtube": yt, "tiktok": tt}


# --------------------------------------------------------------------------- TikTok OAuth
def tiktok_save_app(client_key: str, client_secret: str, redirect_uri: str) -> None:
    client_key, client_secret, redirect_uri = client_key.strip(), client_secret.strip(), redirect_uri.strip()
    if not client_key or not client_secret:
        raise StudioError("client_key et client_secret sont requis (portail TikTok for Developers → ton application).")
    if not redirect_uri.startswith(("http://", "https://")):
        raise StudioError("L'adresse de retour (redirect URI) doit commencer par http:// ou https:// et être déclarée dans le portail.")
    old = _read(TT_APP)
    if old.get("client_key") != client_key:  # autre application : l'ancienne connexion n'est plus valable
        TT_TOKEN.unlink(missing_ok=True)
    _write_private(TT_APP, {"client_key": client_key, "client_secret": client_secret, "redirect_uri": redirect_uri})


def tiktok_auth_url(modes: list[str]) -> str:
    app = _read(TT_APP)
    if not app.get("client_key"):
        raise StudioError("Enregistre d'abord client_key / client_secret de ton application TikTok.")
    scopes = ["user.info.basic"] + (["video.upload"] if "upload" in modes else []) + (["video.publish"] if "publish" in modes else [])
    if len(scopes) == 1:
        scopes.append("video.upload")
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    for k in [k for k, v in _PENDING.items() if time.time() - v["time"] > 900]:
        _PENDING.pop(k, None)
    _PENDING[state] = {"verifier": verifier, "scope": ",".join(scopes), "time": time.time()}
    q = urllib.parse.urlencode({"client_key": app["client_key"], "scope": ",".join(scopes), "response_type": "code",
                                "redirect_uri": app["redirect_uri"], "state": state, "code_challenge": challenge,
                                "code_challenge_method": "S256"})
    return f"{AUTH_URL}?{q}"


def _token_request(form: dict) -> dict:
    code, body = _http("POST", f"{API}/v2/oauth/token/", headers={"Content-Type": "application/x-www-form-urlencoded",
                                                                  "Cache-Control": "no-cache"},
                       data=urllib.parse.urlencode(form).encode())
    if code != 200 or "access_token" not in body:
        raise StudioError(_tt_error(body) if body else f"Échec de la connexion TikTok (HTTP {code}).")
    now = time.time()
    return {"access_token": body["access_token"], "refresh_token": body.get("refresh_token", ""), "open_id": body.get("open_id", ""),
            "scope": body.get("scope", ""), "expires_at": now + int(body.get("expires_in", 86400)),
            "refresh_expires_at": now + int(body.get("refresh_expires_in", 31536000))}


def tiktok_complete(value: str, state: str | None = None) -> dict:
    """`value` : adresse de retour complète (…?code=…&state=…) ou simplement le code."""
    value = value.strip()
    code = value
    if "code=" in value or value.startswith("http"):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(value).query)
        if "error" in q:
            raise StudioError(f"TikTok a refusé l'autorisation : {q['error'][0]} {q.get('error_description', [''])[0]}")
        code = (q.get("code") or [""])[0]
        state = state or (q.get("state") or [None])[0]
    code = urllib.parse.unquote(code)
    if not code:
        raise StudioError("Aucun code d'autorisation trouvé.")
    pend = _PENDING.pop(state, None) if state else None
    if pend is None and not state and len(_PENDING) == 1:  # collage du seul code (sans « state ») : demande en cours
        pend = _PENDING.pop(next(iter(_PENDING)))
    if pend is None:
        raise StudioError("Demande de connexion introuvable ou expirée (15 min) : clique de nouveau sur « Connecter TikTok ».")
    app = _read(TT_APP)
    tok = _token_request({"client_key": app["client_key"], "client_secret": app["client_secret"], "code": code,
                          "grant_type": "authorization_code", "redirect_uri": app["redirect_uri"], "code_verifier": pend["verifier"]})
    tok["scope"] = tok.get("scope") or pend["scope"]
    try:
        tok["nickname"] = tiktok_user_info(tok["access_token"]).get("display_name")
    except StudioError:
        tok["nickname"] = None
    _write_private(TT_TOKEN, tok)
    return {"nickname": tok.get("nickname"), "scope": tok["scope"]}


def tiktok_logout() -> None:
    TT_TOKEN.unlink(missing_ok=True)


def tiktok_access_token() -> str:
    tok, app = _read(TT_TOKEN), _read(TT_APP)
    if not tok.get("access_token"):
        raise StudioError("TikTok n'est pas connecté : page Comptes → Connecter TikTok.")
    if tok.get("expires_at", 0) - time.time() < 300:
        if not tok.get("refresh_token") or tok.get("refresh_expires_at", 0) < time.time():
            raise StudioError(TT_ERRORS["access_token_invalid"])
        new = _token_request({"client_key": app["client_key"], "client_secret": app["client_secret"],
                              "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
        tok.update(new)
        _write_private(TT_TOKEN, tok)
    return tok["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}


def tiktok_user_info(token: str) -> dict:
    code, body = _http("GET", f"{API}/v2/user/info/?fields=open_id,display_name", headers={"Authorization": f"Bearer {token}"})
    if code != 200 or (body.get("error") or {}).get("code") not in (None, "ok"):
        raise StudioError(_tt_error(body))
    return (body.get("data") or {}).get("user") or {}


def tiktok_creator_info(token: str) -> dict:
    code, body = _http("POST", f"{API}/v2/post/publish/creator_info/query/", headers=_auth_headers(token), data=b"{}")
    if code != 200 or (body.get("error") or {}).get("code") not in (None, "ok"):
        raise StudioError(_tt_error(body))
    return body.get("data") or {}


# --------------------------------------------------------------------------- envoi
def plan_chunks(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) selon les règles TikTok : < 5 Mo en un bloc ; sinon blocs de 5 à 64 Mo, le dernier absorbe le reste."""
    if size < 5 * 1024 * 1024:
        return size, 1
    chunk = min(size, 10 * 1024 * 1024)
    return chunk, max(1, size // chunk)


def tiktok_post_video(video: str, caption: str, *, mode: str = "inbox", privacy: str = "SELF_ONLY", ai_label: bool = True,
                      log=print, wait: bool = True) -> dict:
    path = Path(video)
    if not path.is_file():
        raise StudioError(f"Vidéo introuvable : {video}")
    token = tiktok_access_token()
    size = path.stat().st_size
    chunk, count = plan_chunks(size)
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": count}
    if mode == "direct":
        info = tiktok_creator_info(token)
        options = info.get("privacy_level_options") or ["SELF_ONLY"]
        if privacy not in options:
            log(f"[tiktok] confidentialité « {privacy} » non proposée ({', '.join(options)}) : utilisation de « {options[0]} ».")
            privacy = options[0]
        maxd = info.get("max_video_post_duration_sec")
        post_info = {"title": caption[:2200], "privacy_level": privacy, "disable_duet": False, "disable_comment": False,
                     "disable_stitch": False, "video_cover_timestamp_ms": 1000}
        if ai_label:
            post_info["is_aigc"] = True
        body = {"post_info": post_info, "source_info": source}
        url = f"{API}/v2/post/publish/video/init/"
        log(f"[tiktok] publication directe ({privacy}) — compte : {info.get('creator_nickname', '?')}"
            + (f", durée max {maxd}s" if maxd else ""))
    else:
        body = {"source_info": source}
        url = f"{API}/v2/post/publish/inbox/video/init/"
        log("[tiktok] envoi en brouillon (boîte de réception de ton appli TikTok)")
    code, res = _http("POST", url, headers=_auth_headers(token), data=json.dumps(body).encode())
    if code != 200 and mode == "direct" and "is_aigc" in json.dumps(res) + str(res.get("error")):
        log("[tiktok] l'option d'étiquette IA n'est pas acceptée par l'API : active-la à la main dans l'appli avant de publier.")
        body["post_info"].pop("is_aigc", None)
        code, res = _http("POST", url, headers=_auth_headers(token), data=json.dumps(body).encode())
    if code != 200 or (res.get("error") or {}).get("code") not in (None, "ok"):
        raise StudioError(_tt_error(res))
    data = res.get("data") or {}
    publish_id, upload_url = data.get("publish_id"), data.get("upload_url")
    if not publish_id or not upload_url:
        raise StudioError("Réponse TikTok incomplète (pas d'adresse d'envoi).")
    with open(path, "rb") as fh:
        for i in range(count):
            start = i * chunk
            n = chunk if i < count - 1 else size - start  # dernier bloc : tout le reste
            buf = fh.read(n)
            hdr = {"Content-Type": "video/mp4", "Content-Length": str(len(buf)), "Content-Range": f"bytes {start}-{start + len(buf) - 1}/{size}"}
            code, res = _http("PUT", upload_url, headers=hdr, data=buf, timeout=600)
            if code not in (200, 201, 206):
                raise StudioError(f"Envoi du bloc {i + 1}/{count} refusé par TikTok (HTTP {code}).")
            log(f"[tiktok] envoi {int((start + len(buf)) * 100 / size)} %")
    final = {"publish_id": publish_id, "status": "UPLOADED"}
    if wait:
        for _ in range(40):
            time.sleep(3 if API.startswith("https://open.tiktokapis.com") else 0.2)
            code, st = _http("POST", f"{API}/v2/post/publish/status/fetch/", headers=_auth_headers(token),
                             data=json.dumps({"publish_id": publish_id}).encode())
            s = (st.get("data") or {}).get("status", "")
            if s in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                final["status"] = s
                break
            if s == "FAILED":
                raise StudioError(TT_ERRORS.get((st.get("data") or {}).get("fail_reason", ""),
                                                f"TikTok a échoué à traiter la vidéo : {(st.get('data') or {}).get('fail_reason', '?')}"))
        else:
            final["status"] = "PROCESSING"
    return final

# Publier

## Dossier prêt à publier (`publish.py`)
`python3 -I scripts/publish.py out/ [--handle @compte] [--lang fr]` crée `out/publish/NN_slug/` : `video.mp4`, `cover.jpg`,
`youtube.txt` (titre ≤ 100, description, réglages à cocher), `tiktok.txt` (légende + hashtags), `metadata.json`, plus `INDEX.md`.
Titres, descriptions et hashtags sont des propositions tirées de la transcription : Claude ou toi les réécrivez
(titre dans la langue de la vidéo finale) avant d'envoyer. Aucune garantie de portée.

## YouTube (`youtube_upload.py`, gratuit)
API officielle, quota ~6 envois/jour. Mise en place unique : projet Google Cloud → activer YouTube Data API v3 → écran de
consentement (Externe, toi comme utilisateur test) → ID client « Application de bureau » → `client_secret.json`, puis
`pip install google-api-python-client google-auth-oauthlib`.
`python3 -I scripts/youtube_upload.py --from-folder out/publish/01_xxx --client-secret client_secret.json`
Envoi en PRIVÉ par défaut (l'API force le privé tant que le projet n'est pas audité) ; tu passes en public dans YouTube Studio.
Le champ « contenu synthétique » est coché automatiquement quand une voix de synthèse a été utilisée. Non testé sans compte.

## TikTok
L'API d'envoi direct exige une validation de l'application ; sans elle, les vidéos restent privées. Publier depuis
l'application TikTok avec `video.mp4`, `cover.jpg` et `tiktok.txt`, en activant l'étiquette « contenu généré par IA ».

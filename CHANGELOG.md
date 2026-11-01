# Journal des versions — Phenix-video (© 2026 Phenix - kcw)

## 1.3.1

- Correctif : le lien « Télécharger » / la lecture d'un clip échouait quand le nom du fichier contenait `#`, des emoji ou des espaces (titres TikTok). Les liens sont maintenant encodés correctement.
- Les vidéos téléchargées par lien reçoivent un nom simple (identifiant de la vidéo) ; le titre reste lu depuis les métadonnées.

## 1.3.0

- Scoring des moments : nouveaux signaux de rétention/complétion/relecture (gratification rapide, départ immédiat, temps morts pénalisés, fin qui reboucle sur l'accroche, clips courts) — bornés à -10/+12.
- Dossier de publication : `BOOST.md` (fiche de boost Facebook / TikTok : checklist, réglages de départ, lecture des résultats ; aucune dépense automatique).
- Nouveau : `trends.py` et onglet « Tendances » : analyse de liens de vidéos virales (durée, accroches, hashtags, rythme, accroche parlée avec `--deep`), idées de titres/hashtags pour ton sujet, traduction optionnelle. Recherche YouTube gratuite via yt-dlp.
- `./phenix trends …` ; `selftest` couvre la publication (boost) et les tendances.

## 1.2.1

- Correctif : « Le transcript ne contient aucun mot horodaté » sur les vidéos sans parole (sport, musique) ou plus courtes que la durée minimale. Nouveau mode « sans parole » : sélection des moments par énergie sonore + mouvement, clip unique si la vidéo est courte, sous-titres/doublage/traduction désactivés automatiquement.
- Le resserrage (jump-cuts) ne bloque plus le clip en cas d'échec.
- Nouveau : `./phenix selftest` (auto-test de bout en bout).
- Appli web : affiche la ligne d'erreur claire en cas d'échec.
- doctor : indication GPU/CPU corrigée.

## 1.2.0
- Mode téléphone : `./phenix app --lan` (code PIN, limitation d'essais) + application installable sur l'écran d'accueil Android (PWA).
- Windows : lanceur `PhenixVideo.exe` construit par GitHub Actions (`.github/workflows/build-windows.yml`).
- Documentation : `docs/ANDROID.md`, `docs/WINDOWS.md`.

## 1.1.0
- `./phenix` : lanceur unique (app, doctor, clips, enhance, publish, update).
- `scripts/doctor.py` : diagnostic d'installation avec la commande de réparation pour chaque manque.
- `update.sh` : mise à jour depuis GitHub + dépendances.
- Application : si le port 8765 est occupé, un port libre est choisi automatiquement.
- Installateur : PyTorch CPU d'abord (plus de téléchargement NVIDIA), reprises réseau, diagnostic final.
- Documentation WSL complète (`docs/WSL.md`).

## 1.0.0
- Clips verticaux 1080p, sous-titres animés, traduction EN↔FR, doublage F/M, montage dynamique, nettoyage, effets, fond,
  mascotte, stickers, dossier de publication, envoi YouTube, application locale.

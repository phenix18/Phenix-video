---
name: phenix-video
description: Studio vidéo local et gratuit de montage et d'extraction automatique de clips. Prend un fichier OU un lien (YouTube, TikTok, Instagram, X, Vimeo…) et transforme la vidéo en clips verticaux 1080p (détection des meilleurs moments, cadrage intelligent sur le visage, sous-titres animés mot par mot), traduit (EN↔FR et autres), change la voix off (doublage par voix de synthèse) et offre des outils de montage (coupe, jump-cuts, vitesse, transitions, musique avec ducking, titres, zooms, filigrane, miniature). À utiliser dès qu'on parle de clips TikTok/Reels/Shorts, de sous-titres, de doublage, de traduction de vidéo, de voix off ou de montage, sans API payante.
---

# Phenix-video

Tout tourne en local : FFmpeg + Python libre. Aucune clé API, aucun abonnement.
Scripts dans `scripts/` (à lancer avec `python3 -I <chemin>/scripts/<script>.py`).

## Démarrage rapide

```sh
# 1. Choisir les moments forts, sans rendre (relecture possible)
python3 -I scripts/pipeline.py video.mp4 -o out --stop-after clips

# 2. Rendre les clips validés en 1080x1920
python3 -I scripts/pipeline.py video.mp4 -o out --clips-file out/clips.json

# Depuis un lien YouTube / TikTok / Instagram (téléchargé en 1080p max, --max-height 2160 pour la 4K) :
python3 -I scripts/pipeline.py "https://www.youtube.com/watch?v=XXXX" -o out --stop-after clips
python3 -I scripts/fetch.py "https://www.tiktok.com/@compte/video/123" -o downloads   # téléchargement seul

# Tout d'un coup, sous-titres traduits en français :
python3 -I scripts/pipeline.py video.mp4 -o out --translate-to fr

# Avec voix off française de synthèse :
python3 -I scripts/pipeline.py video.mp4 -o out --translate-to fr --dub
```

# Recette « doublage + sous-titres traduits + montage dynamique » (EN→FR ou FR→EN) :
python3 -I scripts/pipeline.py video.mp4 -o out --clips-file out/clips.json \
    --tighten --translate-to fr --dub --voice-gender both      # versions _F (féminine) et _M (masculine)

Installation et dépendances : `references/setup.md` (FFmpeg, `pip install -r requirements.txt`).

## Ce que Claude doit faire (workflow recommandé)

1. **Vérifier l'environnement** : `ffmpeg -version`, `pip list | grep -i faster-whisper`. Si un paquet manque, l'installer (voir setup).
2. **Lancer `--stop-after clips`**, puis **lire `out/clips.json` et les `text`/`reasons` de chaque clip**. Le score est une heuristique : Claude est le juge final. Il peut re-classer, supprimer un clip qui commence au milieu d'une idée, ajuster `start`/`end` aux limites de phrase, et réécrire les `title` en accroches courtes. Voir `references/virality-heuristics.md`.
3. **Rendre** avec `--clips-file out/clips.json` (le fichier édité). Les champs `id`, `title`, `duration` sont facultatifs ; `start` et `end` sont obligatoires.
4. **Contrôler** : extraire 2-3 images (`ffmpeg -ss 5 -i clip.mp4 -frames:v 1 f.png`), les regarder (cadrage, sous-titres lisibles et dans la zone sûre), lire `report.md` (avertissements de résolution).
5. **Livrer** les `.mp4` (+ `.jpg` miniature) avec une ligne de contexte par clip.

## Durées

Par défaut les clips font **75 s minimum (1 min 15) et 180 s maximum**, cible 100 s. Pour des formats courts : `--short` (20-60 s) ou `--min/--max/--target`. Si l'utilisateur demande « minimum 1,15 » sans unité, confirmer : 1 min 15 est l'interprétation retenue. Vérifier les durées maximales actuelles de chaque plateforme (elles changent).

## Liens (YouTube, TikTok…)

`fetch.py` (yt-dlp) télécharge la meilleure qualité ≤ `--max-height` (H.264 de préférence) et écrit `<nom>.info.json`. Le pipeline accepte directement un lien comme entrée. Vidéo privée ou limitée par l'âge : `--cookies-from-browser chrome`. Une vidéo TikTok est déjà en 9:16 : le mode `auto` ne recadre pas, il met à l'échelle en 1080x1920 (avertissement si la source est plus petite, souvent 576p/720p). **Droits** : ne traiter que des contenus que l'utilisateur possède ou est autorisé à réutiliser ; rappeler que les conditions des plateformes s'appliquent. Si le téléchargement échoue (réseau filtré, plateforme qui bloque yt-dlp, `pip install -U yt-dlp` règle souvent le problème), demander le fichier directement.

## Qualité 1080p

- Sortie : **1080x1920** (9:16), **1920x1080** (16:9), 1080x1080 (1:1), 1080x1350 (4:5). H.264 High, CRF 18, 30 fps (ou fps source si 24-60), AAC 256 kb/s, loudnorm -14 LUFS. `--quality max|high|balanced|fast`.
- **Limite physique** : un recadrage 9:16 d'une source 1080p 16:9 n'utilise que ~608 px de large, agrandis vers 1080 → image un peu douce. Pour une netteté maximale : source 4K, ou `--mode blur` (vidéo entière nette au centre sur fond flou). Le rapport signale cet avertissement.

## Modes de cadrage (`--mode`)

`auto` (défaut : suit les visages si détectés, sinon fond flou) · `track` (caméra virtuelle stable) · `center` · `blur` · `fit` · `none` (16:9 sans recadrage). La détection de visages utilise YuNet (OpenCV, téléchargé une fois, ~230 Ko) ; sans lui, repli sur le fond flou/centre.

## Sous-titres (`--style`)

`pop` (MAJUSCULES, mot actif jaune, style Hormozi) · `karaoke` · `clean` (bandeau) · `minimal`. Options : `--highlight "#FF3B30"`, `--font`, `--no-captions`. Détails : `references/captions-styles.md`.

## Traduction et voix off

- **Sous-titres traduits** : `--translate-to fr|en|es|ar|…` (la voix d'origine est conservée).
- **Voix off de remplacement** : ajouter `--dub`. Voix : `--voice` (`dub.py --list-voices`), hauteur : `--pitch -2` (plus grave), moteur : `--tts-engine piper|edge|espeak`. Le son d'origine est baissé sous la voix (`--bg duck`), supprimé (`--bg none`) ou débarrassé de la voix avec demucs (`--separate`).
- **Traduction manuelle de qualité** : `--translate-engine manual` écrit `<clip>.to_translate.json` ; Claude traduit les phrases (en visant la durée d'origine, voir `max_words_hint`) et écrit `<clip>.translated.json` (`[{"id":0,"text":"…"}]`), puis on relance la même commande.
- **Voix au choix** : `--voice-gender female|male|both` (both produit `_F.mp4` et `_M.mp4` à comparer). Voix par défaut FR : siwis (F) / tom (M) ; EN : lessac (F) / ryan (M).
- **Montage dynamique** : `--tighten` supprime les blancs entre les mots (jump-cuts pilotés par la transcription, `scripts/polish.py`, `--max-gap` pour régler) avant traduction/doublage ; le transcript est recalé.
- Limites honnêtes : pas de clonage de la voix d'origine ni de synchronisation labiale ; une traduction plus longue que l'original est accélérée jusqu'à x1.35 puis décale les phrases suivantes. Détails : `references/dubbing-and-translation.md`.

## Boîte à outils de montage (`scripts/edit.py`)

| Besoin | Commande |
|---|---|
| Couper | `edit.py trim in.mp4 -o out.mp4 --start 5 --end 20` |
| Assembler + transition | `edit.py concat a.mp4 b.mp4 -o out.mp4 --xfade fade --size 1920x1080` |
| Vitesse | `edit.py speed in.mp4 -o out.mp4 --factor 1.25` |
| Jump-cuts (enlever les blancs) | `edit.py silence in.mp4 -o out.mp4 [--threshold -35dB]` |
| Musique + ducking | `edit.py music in.mp4 --track bg.mp3 -o out.mp4 --volume 0.15` |
| Titre animé | `edit.py text in.mp4 -o out.mp4 --text "Titre" --start 0 --end 3 --box` |
| Zoom d'emphase | `edit.py punch in.mp4 -o out.mp4 --at 3.2,9.5` |
| Changeur de voix | `edit.py voice in.mp4 -o out.mp4 --preset deep` (deep, low, high, child, radio, echo, robot) |
| Volume normalisé | `edit.py loudnorm in.mp4 -o out.mp4` |
| Incruster des sous-titres | `edit.py burn in.mp4 --subs s.srt -o out.mp4` |
| Logo / filigrane | `edit.py logo in.mp4 --image logo.png -o out.mp4 --position br` |
| Stabiliser | `edit.py stabilize in.mp4 -o out.mp4` (nécessite libvidstab) |
| Miniature | `edit.py thumbnail in.mp4 -o cover.jpg` |

Scripts unitaires : `fetch.py`, `polish.py`, `fx.py`, `background.py`, `characters.py`, `enhance.py`, `publish.py`, `youtube_upload.py`, `app.py`, `transcribe.py`, `highlights.py`, `translate.py`, `dub.py`, `captions.py`, `render.py` (chacun a `--help`).

## Application locale et masquage de ta marque

- `python3 -I scripts/app.py` : interface web locale (voir `references/app-locale.md`), lanceurs Windows/Linux/macOS fournis.
- `edit.py delogo in.mp4 -o out.mp4 --area br [--area tl] [--method blur|delogo|box] [--start 2 --end 9]` : masque **ta propre** marque (logo, nom de compte) dans un coin ou une zone `x,y,l,h`. Ne jamais l'utiliser pour retirer le crédit/filigrane d'un autre créateur ; pour une vidéo TikTok, demander le fichier original sans filigrane à son auteur.

## Effets, nettoyage, fond, personnages, publication

- `enhance.py clip.mp4 -o out.mp4 --clean --bg blur|color:#hex|image:f|video:f --effects cinema,vignette --title "…" --mascot --sticker logo.png@tr,0.15,0,99` (détails : `references/effects-and-characters.md`, catalogue : `fx.py --list`).
- Mascotte originale synchronisée à la voix (`characters.py mascot`), stickers/GIF fournis par l'utilisateur. Ne jamais dessiner de personnage protégé.
- `publish.py out/` : dossier prêt à publier (titres, descriptions, hashtags, miniature). `youtube_upload.py` : envoi YouTube officiel (privé par défaut). TikTok : publication manuelle (`references/publishing.md`).
- Le remplacement de fond n'a pas été validé sur de vraies personnes dans l'environnement de développement : regarder le résultat avant de livrer.

## Règles des plateformes

Lire `references/platform-guidelines.md` avant de livrer : droits, étiquette « contenu IA » pour la voix de synthèse, originalité, musique, checklist. Aucune garantie de « boost » algorithmique ; ne jamais promettre de résultat.

## Règles de travail

- Ne jamais écraser la vidéo d'origine : toutes les sorties vont dans un dossier `-o`. Les rendus passent par un fichier temporaire renommé à la fin (pas de `.mp4` tronqué).
- Respecter les droits : ne traiter que des vidéos dont l'utilisateur détient les droits ; un doublage ne doit pas imiter la voix d'une personne réelle sans son accord.
- Un rendu complet fait attendre : tester d'abord sur un clip (`--clips 1`, ou `--quality fast`), regarder une image, puis lancer le lot en `high`.
- Si une étape échoue (réseau pour télécharger un modèle, paquet manquant), dire précisément laquelle et proposer l'alternative locale du tableau de `references/setup.md`.

---
Phenix-video · © 2026 Phenix - kcw

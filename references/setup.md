# Installation

## 1. FFmpeg (obligatoire)

- Windows : `winget install Gyan.FFmpeg` (build complet, inclut libass, libvidstab, rubberband)
- macOS : `brew install ffmpeg`
- Linux : `sudo apt install ffmpeg` (vérifier `ffmpeg -filters | grep -E "ass|xfade|sidechaincompress"`)

Filtres utilisés : `ass`, `xfade`, `acrossfade`, `sidechaincompress`, `loudnorm`, `silencedetect`, `drawtext`, `gblur`. `vidstab` et `rubberband` sont facultatifs (stabilisation, meilleur changement de hauteur).

## 2. Python 3.10+

```sh
# sans GPU NVIDIA : PyTorch CPU d'abord (évite les gros paquets CUDA)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

| Paquet | Rôle | Alternative si absent |
|---|---|---|
| faster-whisper | transcription mot à mot | `transcribe.py --import-subs fichier.srt` (mots estimés) |
| argostranslate | traduction hors-ligne | `--translate-engine manual` (Claude traduit) |
| piper-tts | voix off hors-ligne | `edge-tts` (en ligne) ou `espeak-ng` (robotique) |
| yt-dlp | télécharger par lien | fournir le fichier vidéo ; `pip install -U yt-dlp` si une plateforme change |
| opencv | recadrage, visages | — (obligatoire pour le mode `track`) |
| demucs (option) | retirer la voix d'origine | `--bg none` ou `--bg duck` |

## 3. Téléchargements au premier usage (une seule fois, puis hors-ligne)

- Modèle Whisper (Hugging Face) : `tiny` ~75 Mo, `base` ~145 Mo, `small` ~480 Mo, `medium` ~1,5 Go.
  Français : `small` suffit pour des voix claires, `medium` pour du bruit/accents.
- Modèle Argos de la paire de langues (~100 Mo) : téléchargé par `translate.py`.
- Voix Piper (~60 Mo) : téléchargée depuis `huggingface.co/rhasspy/piper-voices` dans `~/.cache/phenix-video/piper`.
- Détecteur de visages YuNet (~230 Ko) : `~/.cache/phenix-video/face_detection_yunet_2023mar.onnx`.
  Hors-ligne : copie le fichier à la main (dépôt `opencv/opencv_zoo`, `models/face_detection_yunet`) ou définis `PHENIX_VIDEO_YUNET=/chemin/modele.onnx`.

Si le réseau est filtré (liste blanche), le téléchargement échoue avec un message clair : télécharger le fichier ailleurs et le déposer dans le dossier de cache indiqué.

## 4. Matériel

- CPU seul suffit (Whisper en `int8`). GPU NVIDIA : `--device cuda --compute-type float16` pour transcrire ~10x plus vite.
- Rendu : ~1 à 3 fois la durée du clip en qualité `high` sur un portable ; `--quality balanced` pour accélérer.
- Fonts : Inter par défaut ; sinon passer `--font Arial` (le nom d'une police installée).

## 5. Vérification rapide

```sh
python3 -I scripts/edit.py --help
python3 -I scripts/dub.py --list-voices
```

# Phenix-video

Studio vidéo **local et gratuit** (aucune API payante) : transforme une vidéo (fichier ou lien) en clips verticaux 1080p,
sous-titres animés, traduction EN↔FR et autres, doublage par voix de synthèse (féminine/masculine), montage dynamique,
nettoyage, effets, fond au choix, mascotte, stickers et dossier prêt à publier pour YouTube / TikTok.

© 2026 Phenix - kcw. Tous droits réservés (voir `LICENSE`, `NOTICE.md`).

## Installation (WSL / Ubuntu / macOS)
```bash
git clone https://github.com/phenix18/Phenix-video.git && cd Phenix-video
chmod +x installer.sh lancer.sh && ./installer.sh
./lancer.sh --no-browser        # puis ouvrir http://127.0.0.1:8765
```
Windows natif : `INSTALLER_WINDOWS.bat` puis `LANCER_WINDOWS.bat`.

## En ligne de commande
```bash
. .venv/bin/activate
python scripts/pipeline.py video.mp4 -o out --stop-after clips
python scripts/pipeline.py video.mp4 -o out --clips-file out/clips.json --tighten --translate-to fr --dub --voice-gender both
python scripts/enhance.py out/clip.mp4 -o clip_pro.mp4 --clean --effects cinema --mascot
python scripts/publish.py out/
```
Comme skill Claude Code : cloner ce dépôt dans `~/.claude/skills/phenix-video`.

## À respecter
Ne traiter que des vidéos dont tu détiens les droits ou l'autorisation. Activer l'étiquette « contenu IA » pour les voix de
synthèse. Aucune garantie de portée sur les plateformes. Détails : `references/platform-guidelines.md`.

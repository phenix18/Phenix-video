# Phenix-video

Studio vidéo **local et gratuit** (aucune API payante) : transforme une vidéo (fichier ou lien) en clips verticaux 1080p,
sous-titres animés, traduction EN↔FR et autres, doublage par voix de synthèse (féminine/masculine), montage dynamique,
nettoyage, effets, fond au choix, mascotte, stickers et dossier prêt à publier pour YouTube / TikTok.

© 2026 Phenix - kcw. Tous droits réservés (voir `LICENSE`, `NOTICE.md`).

## Installation (WSL / Ubuntu / macOS) — voir `docs/WSL.md`
```bash
git clone https://github.com/phenix18/phenix-video.git && cd phenix-video
./installer.sh
./phenix doctor                 # diagnostic
./phenix app --no-browser       # puis ouvrir http://127.0.0.1:8765
./phenix update                 # mises à jour
```
Windows natif : `INSTALLER_WINDOWS.bat` puis `LANCER_WINDOWS.bat`.

## Windows (.exe) et Android
- Windows : `PhenixVideo.exe` (construit par GitHub Actions) ou `INSTALLER_WINDOWS.bat` — `docs/WINDOWS.md`.
- Android : le téléphone sert d'écran, le PC fait le travail : `./phenix app --lan` puis « Ajouter à l'écran d'accueil » — `docs/ANDROID.md`.

## En ligne de commande
```bash
./phenix clips video.mp4 -o out --stop-after clips
./phenix clips video.mp4 -o out --clips-file out/clips.json --tighten --translate-to fr --dub --voice-gender both
./phenix enhance out/clip.mp4 -o clip_pro.mp4 --clean --effects cinema --mascot
./phenix desktop                 # application PC : fenêtre dédiée (raccourci : ./phenix desktop --install-shortcut)
./phenix publish out/            # + BOOST.md (fiche de boost Facebook/TikTok)
./phenix insights profile https://www.tiktok.com/@moncompte -o analyse   # meilleurs jours/heures, niche, planning .ics
./phenix trends https://… https://… -o tendances --theme "l'argent" --translate-to en   # style des vidéos virales
```
Comme skill Claude Code : cloner ce dépôt dans `~/.claude/skills/phenix-video`.

## À respecter
Ne traiter que des vidéos dont tu détiens les droits ou l'autorisation. Activer l'étiquette « contenu IA » pour les voix de
synthèse. Aucune garantie de portée sur les plateformes. Détails : `references/platform-guidelines.md`.


## Profil, niches, horaires et envoi direct (1.5)

- Page **Profil & niches** : colle le lien d'un profil public → jours/heures qui performent, durée, accroches, hashtags, planning de la semaine et fichier agenda (.ics). « Niches » compare des thèmes (demande, chances pour un petit compte, fraîcheur).
- Page **Comptes** : connecte YouTube (fichier `client_secret.json` Google, gratuit) et TikTok (app développeur gratuite, Login Kit + Content Posting API). Page **Publication** : envoie le clip préparé en un clic.
- Limites honnêtes : analyses = corrélations sur données publiques ; sur YouTube les heures ne sont souvent pas publiques ; TikTok n'autorise la publication directe publique qu'aux apps auditées (sinon brouillon ou « Moi seul »).

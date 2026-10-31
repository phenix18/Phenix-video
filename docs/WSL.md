# Phenix-video sur WSL (Ubuntu) — commandes complètes
© 2026 Phenix - kcw

## 1. Une seule fois : installer WSL (PowerShell administrateur)
```powershell
wsl --install -d Ubuntu
```
Redémarre, ouvre « Ubuntu », crée ton utilisateur.

## 2. Récupérer le projet
```bash
cd ~
git clone https://github.com/phenix18/phenix-video.git
cd phenix-video
```
Dépôt privé : GitHub demande ton identifiant et un **jeton d'accès personnel** (Settings → Developer settings → Tokens) à la place du mot de passe.

## 3. Installer (quelques minutes, gratuit)
```bash
./installer.sh
```
Si le réseau coupe : relance la même commande, pip reprend les téléchargements.

## 4. Vérifier
```bash
./phenix doctor
```

## 5. Utiliser
```bash
./phenix app --no-browser            # puis ouvrir http://127.0.0.1:8765 dans Chrome/Edge (Windows)
```
Ou en commandes (fichiers Windows : /mnt/c/Users/digis/Videos/...) :
```bash
V=/mnt/c/Users/digis/Videos/ma_video.mp4
./phenix clips "$V" -o ~/sortie --stop-after clips                       # voir les moments choisis
./phenix clips "$V" -o ~/sortie --clips-file ~/sortie/clips.json \
        --tighten --translate-to fr --dub --voice-gender both            # EN->FR, voix F et M
./phenix clips "$V" -o ~/sortie --clips-file ~/sortie/clips.json \
        --tighten --translate-to en --dub --voice-gender both            # FR->EN
./phenix enhance ~/sortie/clip_01_*_F.mp4 -o ~/clip_pro.mp4 --clean --effects cinema,vignette --mascot
./phenix publish ~/sortie                                                 # dossier prêt à publier
```
Récupérer les résultats côté Windows : `explorer.exe ~/sortie` (ou `\\wsl$\Ubuntu\home\<utilisateur>\sortie`).

## 6. Mettre à jour
```bash
cd ~/phenix-video && ./phenix update
```

## Dépannage
| Symptôme | Commande |
|---|---|
| Port 8765 occupé | rien à faire : l'application choisit le port suivant ; ou `pkill -f scripts/app.py` |
| `python: not found` | utilise `./phenix ...` (il active l'environnement) |
| Téléchargement NVIDIA/torch coupé | `. .venv/bin/activate && pip install torch --index-url https://download.pytorch.org/whl/cpu` puis `./installer.sh` |
| Page inaccessible depuis Windows | `wsl --update` puis `wsl --shutdown` (PowerShell) et relance |
| Manque FFmpeg | `sudo apt install -y ffmpeg` |

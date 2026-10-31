# Phenix-video sur Windows (.exe)
© 2026 Phenix - kcw

## Obtenir PhenixVideo.exe
Le .exe est construit par GitHub (gratuit) :
1. Sur le dépôt : onglet **Actions** → **build-windows** → **Run workflow** (ou crée une version : `git tag v1.2.0 && git push --tags`).
2. Quand c'est vert, ouvre l'exécution → section **Artifacts** → télécharge `Phenix-video-windows` (ou, pour un tag `v*`, la page **Releases**).
3. Dézippe **toute** l'archive (le .exe a besoin du dossier `scripts` à côté de lui) puis double-clique sur `PhenixVideo.exe`.

## Premier lancement
Il vérifie Python et FFmpeg (installés avec winget si absents : ferme puis relance), crée un environnement dans
`%LOCALAPPDATA%\PhenixVideo` et installe les dépendances (quelques minutes, une seule fois). Puis le navigateur s'ouvre sur l'application.
Pour le téléphone : lance depuis un terminal `PhenixVideo.exe --lan` (voir `docs/ANDROID.md`).

## Limites
- Ce n'est pas un exécutable « tout-en-un » : il installe Python/FFmpeg/dépendances (plusieurs Go avec les modèles) au lieu de les embarquer.
- Windows Defender / SmartScreen peut signaler un .exe non signé : « Informations complémentaires » → « Exécuter quand même ».
- Cette chaîne de construction n'a pas pu être testée depuis mon environnement (Linux) : si le build échoue, envoie-moi le journal.
- Sans .exe : `INSTALLER_WINDOWS.bat` puis `LANCER_WINDOWS.bat` font la même chose.

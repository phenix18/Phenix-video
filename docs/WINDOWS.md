# Phenix-video sur Windows (application PC)
© 2026 Phenix - kcw

L'application s'ouvre dans **sa propre fenêtre** (comme un logiciel), 100 % en local. Trois façons de l'obtenir, de la plus simple à la plus manuelle.

## 1. Installateur `Phenix-video-Setup.exe` (recommandé)
Construit par GitHub (gratuit) :
1. Dépôt → onglet **Actions** → **build-windows** → **Run workflow** (ou crée une version : `git tag v1.4.0 && git push --tags`).
2. Quand c'est vert : exécution → **Artifacts** (ou page **Releases** pour un tag) → télécharge `Phenix-video-Setup.exe`.
3. Double-clique : installation sans droits administrateur, raccourcis **Bureau** et **menu Démarrer** avec l'icône Phenix-video.
4. Au premier lancement : installation des composants (Python/FFmpeg via winget si absents, environnement dans `%LOCALAPPDATA%\PhenixVideo`, dépendances). Quelques minutes, une seule fois. Ensuite : clic sur le raccourci → la fenêtre s'ouvre, sans console.

## 2. Archive `Phenix-video-windows.zip`
Même contenu sans installateur : dézippe **tout** le dossier, double-clique sur `PhenixVideo.exe` (il crée les raccourcis lui-même).

## 3. Sans .exe (WSL ou Windows natif)
- Windows natif : `INSTALLER_WINDOWS.bat` (une fois) puis le raccourci **Phenix-video** du Bureau (ou `LANCER_WINDOWS.bat`).
- WSL : `./installer.sh` puis `./phenix desktop` (fenêtre via WSLg sous Windows 11) ou `./phenix app --no-browser` + navigateur Windows.

## Fenêtre native ou mode application
`scripts/desktop.py` essaie dans l'ordre : fenêtre native (module `pywebview`, installé automatiquement si possible) → mode application d'**Edge / Chrome** (fenêtre sans barre d'adresse, rien à installer) → navigateur par défaut. Fermer la fenêtre arrête le serveur local.

## Ce que contient l'application
Clips & doublage (lien ou fichier, 9:16 1080p, sous-titres animés, traduction, voix off de synthèse, resserrage), Masquer ma marque, Améliorer (nettoyage, effets, arrière-plan, mascotte, sticker), **Tendances** (analyse de vidéos virales), **Outils** (couper, vitesse, jump-cuts, musique, titre, zooms, voix, volume, logo, sous-titres, stabilisation, miniature), **Réglages** (diagnostic, auto-test, envoi YouTube), dossier de publication avec fiche de boost.

## Limites
- Ce n'est pas un exécutable « tout-en-un » : il installe Python/FFmpeg/dépendances (plusieurs Go avec les modèles) au lieu de les embarquer.
- Windows SmartScreen peut signaler un .exe non signé : « Informations complémentaires » → « Exécuter quand même ».
- La chaîne de construction Windows (PyInstaller + Inno Setup) n'a pas pu être exécutée depuis mon environnement Linux : si le build échoue, envoie-moi le journal de l'onglet Actions.

# Application locale

`scripts/app.py` ouvre une interface web sur http://127.0.0.1:8765 (aucune dépendance en plus de Python).
Elle n'écoute que sur ta machine. Fichiers et résultats : `~/PhenixVideo/` (`--workdir` pour changer).

- Windows : double-clic `INSTALLER_WINDOWS.bat` (une fois) puis `LANCER_WINDOWS.bat`.
- Linux / macOS : `./installer.sh` puis `./lancer.sh`.
- Sans le script de lancement : `python3 -I scripts/app.py [--port 9000] [--workdir D:/Studio]`.

Onglets : « Améliorer » (nettoyage, fond, effets, mascotte, stickers) ; bouton « dossier de publication » après un traitement de clips ;
 « Clips & doublage » (pipeline complet, ou « Analyser seulement ») et « Masquer ma marque »
(`edit.py delogo`, réservé à tes propres logos/noms de compte).

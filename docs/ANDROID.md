# Phenix-video et Android
© 2026 Phenix - kcw

## Ce qui est réaliste
Le moteur (transcription Whisper, traduction, voix, FFmpeg, MediaPipe) est lourd : il tourne bien sur un PC (Windows/WSL),
pas dans une application Android native. La solution fournie : **le téléphone sert d'écran et de télécommande**, le PC fait le travail.

## Méthode recommandée : navigateur du téléphone + PC sur le même Wi-Fi
1. Sur le PC (WSL) : `./phenix app --lan` — le terminal affiche une adresse (ex. `http://192.168.1.20:8765`) et un **code PIN**.
2. Sur le téléphone (même Wi-Fi), ouvre l'adresse dans Chrome, entre le code.
3. Chrome → menu ⋮ → **Ajouter à l'écran d'accueil** : l'application s'installe avec son icône. Tu peux envoyer des vidéos de la galerie,
   lancer le traitement et télécharger les clips sur le téléphone.

### Si tu utilises WSL2 : rendre le port accessible au téléphone
WSL2 a son propre réseau ; le téléphone ne le voit pas directement. Au choix :
- **Windows 11 22H2+ (simple)** : crée/édite `C:\Users\digis\.wslconfig` :
  ```
  [wsl2]
  networkingMode=mirrored
  ```
  puis dans PowerShell : `wsl --shutdown` et relance Ubuntu.
- **Sinon (redirection de port, PowerShell administrateur)** :
  ```powershell
  $ip = (wsl hostname -I).Split(" ")[0]
  netsh interface portproxy add v4tov4 listenport=8765 listenaddress=0.0.0.0 connectport=8765 connectaddress=$ip
  New-NetFirewallRule -DisplayName "Phenix-video" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
  ```
  (l'adresse WSL change après un redémarrage : refaire la première ligne et la commande `netsh`). Pour annuler :
  `netsh interface portproxy delete v4tov4 listenport=8765 listenaddress=0.0.0.0`
- Utilise ensuite l'adresse **Wi-Fi du PC** (`ipconfig`, ligne « Adresse IPv4 ») avec le port 8765.

### Sécurité
Le mode `--lan` est protégé par un code PIN (5 essais, puis blocage d'une minute) mais **n'est pas chiffré** (HTTP) :
seulement sur un Wi-Fi de confiance, jamais sur un Wi-Fi public. Arrête l'application quand tu as fini (`Ctrl+C`).
Ne l'expose pas sur Internet.

## Ce qui n'est pas fourni (honnêtement)
- **APK natif avec le moteur embarqué** : non réaliste (Whisper/PyTorch/MediaPipe sur Android) et non testé ici.
- **Termux** : seuls les outils FFmpeg simples (`edit.py`, `fx.py`) ont une chance d'y tourner ; la transcription, la traduction
  et le doublage ne sont pas supportés. Non testé.
- **APK « coque »** (une application Android qui ouvre l'adresse du PC) : faisable avec Flet ou Android WebView, mais l'installation
  sur l'écran d'accueil ci-dessus fait déjà la même chose sans compilation. Dis-moi si tu veux quand même un APK.

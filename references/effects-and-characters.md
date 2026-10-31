# Effets, nettoyage, fond, personnages

Tout est local et gratuit. Une commande qui enchaîne tout : `scripts/enhance.py` (ordre : fond → nettoyage/effets/titre → mascotte → stickers).

```sh
python3 -I scripts/enhance.py clip.mp4 -o clip_pro.mp4 --clean --bg blur --effects cinema,vignette \
    --title "Mon titre" --mascot --sticker logo.png@tr,0.15,0,99
python3 -I scripts/fx.py --list        # catalogue d'effets
```

## Effets (`fx.py`)
vignette, warm, cool, cinema, vivid, bw, grain, sharpen, glitch, shake, flash, zoomin, fade, lowlight. Ils s'additionnent.
`--title` : titre animé (fondu) pendant 3 s en haut de l'image.

## Nettoyage (`--clean`)
Audio : filtre grave, réduction de bruit, compression douce, volume -14 LUFS. Image : débruitage léger, netteté, contraste.
Limites : un son très bruyant ne devient pas un son de studio ; rien ne rend nette une image floue au départ.
Stabilisation : `edit.py stabilize` (libvidstab). Ne sert pas à retirer le filigrane ou le crédit d'un autre créateur.

## Arrière-plan (`background.py`, `--bg`)
`blur`, `color:#RRGGBB`, `image:fichier`, `video:fichier` (en boucle). Détection de la personne par MediaPipe (modèle
`selfie_segmenter.tflite`, 250 Ko, `~/.cache/phenix-video`). Pour une personne face caméra ; cheveux fins, mains
devant un fond chargé et vêtements de la couleur du fond donnent des bords moins propres. Le script prévient quand presque
personne n'est détecté. Plus lent que les autres étapes (CPU).

## Personnages (`characters.py`)
- `mascot` : mascotte ORIGINALE (chacal doré/anthracite), bouche synchronisée au volume de la voix, clignement, rebond.
  `characters.py preview mascot.png` en donne un aperçu. Position `br|bl|tr|tl|bc|tc|center`, `--scale`, `--start/--end`.
- `sticker` : ton image PNG/GIF (logo, emoji, mascotte de ta marque) avec position, taille, plage de temps, fondu d'entrée.
- Pas de personnages protégés (dessins animés, films, jeux). Pas de génération de personnages par IA (GPU/API payante).

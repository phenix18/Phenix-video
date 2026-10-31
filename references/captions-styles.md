# Styles de sous-titres

Format ASS brûlé par FFmpeg (`ass=`), taille calculée sur la hauteur de la vidéo (nette en 1080p).

| Style | Rendu | Quand |
|---|---|---|
| `pop` | MAJUSCULES, 1-3 mots, mot actif en jaune, petite animation d'apparition, contour noir épais | contenu énergique, business, motivation |
| `karaoke` | phrase de 4-7 mots, remplissage progressif vert du mot en cours | musique, storytelling |
| `clean` | 2 lignes blanches sur bandeau semi-transparent | interviews, formations |
| `minimal` | texte fin avec ombre | podcasts, contenu sobre |

## Réglages

- `--highlight "#FF3B30"` : couleur du mot actif (hex `#RRGGBB`).
- `--font "Montserrat"` : police installée. Avec une police hors système, ajouter `--fontsdir dossier/` à `render.py`.
- Position : zone sûre ≈ 70 % de la hauteur (au-dessus de l'interface de la plateforme), marges latérales 6 %.
- Arabe / langues RTL : choisir une police qui supporte l'écriture (ex. Noto Sans Arabic) ; `libass` gère le sens de lecture.

## Générer à part

```sh
python3 -I scripts/captions.py transcript.json -o clip.ass --start 120 --end 200 --style pop --size 1080x1920
python3 -I scripts/edit.py burn video.mp4 --subs clip.ass -o video_sub.mp4
```

Sous-titres traduits : passer le transcript produit par `translate.py` (`*.fr.json`) ; après doublage, utiliser `<clip>.transcript.json` (horodatage recalé sur la nouvelle voix).

# Traduction et voix off

## Chaîne

`transcript.json` → phrases (`translate.py`) → traduction → synthèse vocale (`dub.py`) → calage dans le temps → mixage avec le fond sonore → rendu avec sous-titres recalés sur la nouvelle voix.

## Moteurs de traduction

| Moteur | Qualité | Réseau | Usage |
|---|---|---|---|
| `argos` | correcte (contenu simple, EN↔FR bon) | téléchargement du modèle 1 fois | automatique |
| `manual` | la meilleure (Claude traduit en gardant le ton) | aucun | export `to_translate.json` → import `translated.json` |

Langues : codes ISO (`fr`, `en`, `es`, `ar`, `pt`, `de`, `it`…). Si Argos n'a pas la paire directe, passage par l'anglais.

Conseils pour une traduction doublable : garder des phrases courtes, viser la durée d'origine (`max_words_hint` ≈ 3 mots/s), éviter les noms propres traduits, écrire les chiffres en toutes lettres si le moteur les lit mal.

## Voix

| Moteur | Hors-ligne | Qualité | Notes |
|---|---|---|---|
| `piper` | oui | bonne, régulière | voix libres ; `fr_FR-siwis-medium` (femme), `fr_FR-upmc-medium`, `fr_FR-gilles-low` (homme), `en_US-lessac-medium`, `en_US-ryan-high` |
| `edge` | non | très naturelle | gratuit sans clé mais service non officiel (peut changer) ; `fr-FR-DeniseNeural`, `fr-FR-HenriNeural`, `en-US-GuyNeural` |
| `espeak` | oui | robotique | dépannage |

Lister : `dub.py --list-voices`. Catalogue Piper : https://huggingface.co/rhasspy/piper-voices.

Changer le timbre : `--pitch -3` (plus grave) / `+3` (plus aigu) sur la voix de synthèse. Pour modifier la voix d'origine d'une vidéo : `edit.py voice … --preset deep`.

## Calage (comment ça tient dans le temps)

Pour chaque phrase : durée de la synthèse vs temps disponible. Si trop long → accélération jusqu'à `--max-speed` (1,35) ; si ça déborde encore → la phrase suivante est décalée (jamais coupée). Le rapport donne l'accélération moyenne/maximale et le nombre de débordements. Au-delà de x1,25 la voix devient pressée : raccourcir la traduction.

## Fond sonore

`--bg duck` (défaut) garde l'audio d'origine à 18 % et le baisse sous la voix ; l'ancienne voix reste donc faiblement audible. `--bg none` supprime tout. `--separate` (demucs) retire la voix d'origine et conserve musique/ambiance : le plus propre, mais lourd.

## Limites à annoncer à l'utilisateur

- Pas de clonage de la voix d'origine ni de synchronisation labiale.
- Une voix de synthèse n'a pas les émotions d'un locuteur ; privilégier `edge` pour le naturel, `piper` pour l'autonomie.
- Ne pas imiter la voix d'une personne réelle sans son accord ; indiquer au public quand une voix est synthétique si la plateforme l'exige.

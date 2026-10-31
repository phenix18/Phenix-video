# Choisir les bons moments

`highlights.py` note chaque fenêtre de phrases (0-100). Il explique son score dans `reasons`. Claude doit relire et décider.

## Barème (résumé)

| Critère | Points | Idée |
|---|---|---|
| Accroche (1re phrase) | 0-25 | question, formule d'attention (« le secret… », « personne ne… »), chiffre, phrase courte |
| Mots forts | 0-20 | argent, peur, erreur, vérité, résultat… (extensible : `--lexicon`) |
| Rythme | 0-15 | idéal ≈ 2,2 à 3,6 mots/s |
| Densité de parole | 0-10 | peu de silences |
| Longueur | 0-10 | proche de `--target` |
| Fin satisfaisante | 0-10 | phrase terminée, conclusion nette |
| Ponctuation expressive | 0-5 | `!` et `?` |
| Énergie vocale | 0-5 | si `--media` fourni |
| Pénalités | – | commence par « et/mais/donc », tics de langage, transcription douteuse, coupe en pleine phrase |

## Checklist de relecture (Claude)

1. Le clip se comprend-il **sans** le contexte de la vidéo ? Sinon : décaler `start` vers l'idée de départ ou rejeter.
2. Les **3 premières secondes** donnent-elles envie de rester ? Sinon : commencer à la phrase d'accroche.
3. La fin boucle-t-elle ou conclut-elle ? Couper juste après la chute.
4. Deux clips disent-ils la même chose ? En garder un.
5. Titre : ≤ 60 caractères, promesse ou question, pas de clickbait mensonger.
6. Sujets sensibles (santé, finance, politique) : vérifier que l'extrait ne déforme pas le propos.

## Ajuster

Éditer `clips.json` (`start`, `end`, `title`) ; aligner `start`/`end` sur des limites de phrase du transcript (les `start` des segments). Marge conseillée : 0,2 s avant, 0,4 s après.

## Durées

75-180 s par défaut ; `--short` pour 20-60 s. Au-delà de 90 s, soigner le rythme (zooms `punch`, `silence` pour les jump-cuts) pour garder l'attention.

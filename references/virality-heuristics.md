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
| Signaux de rétention (v1.3) | -10 à +12 | gratification rapide (mot fort/chiffre dans les 5 s), départ immédiat, fin qui reboucle sur l'accroche, clip court (complétion) ; pénalités : silence d'ouverture, temps morts > 1,8 s |
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

## Ce que les plateformes disent mesurer (sources officielles/recherchées, à revérifier)

- **TikTok** : interactions (j'aime, commentaires, partages, vidéos regardées en entier ou rejouées), informations de la vidéo (légende, sons, hashtags), réglages de l'appareil/compte (poids faible). Le nombre d'abonnés n'est pas un facteur direct. Contenu non original ou spam = non éligible aux recommandations ; la diversité du fil est recherchée.
- **YouTube Shorts** : le public « est » l'algorithme : vu vs balayé, durée de visionnage, tests de diffusion initiaux sur un petit groupe. Les contenus originaux sont favorisés.
- **Facebook / TikTok boost** : publicité payante, distincte de l'organique (voir `BOOST.md` du dossier de publication).

Traduction en règles de montage (c'est ce que `highlights.py` récompense) : accroche dans la 1re seconde, valeur ou résultat tôt, aucun temps mort, durée adaptée pour être regardé jusqu'au bout, fin qui donne envie de rejouer ou de commenter. Rien de cela ne garantit la viralité.

## Analyser des vidéos qui marchent (`trends.py`)

Fournir des liens de TA niche. L'outil relève durée, engagement (likes + commentaires / vues), hashtags, formes d'accroche, heure ; avec `--deep` : accroche parlée et nombre de changements de plan. Utiliser le résultat comme **formule** (durée visée, forme d'accroche, rythme, hashtags), jamais pour copier textes, voix ou images d'un autre créateur.

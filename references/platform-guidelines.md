# Publier sur TikTok / YouTube / Instagram en respectant les règles

Aucun outil ne peut **garantir** qu'un algorithme « boostera » une vidéo : les plateformes recommandent ce que les spectateurs regardent jusqu'au bout, commentent, partagent et revoient. Ce skill optimise ce qui dépend de toi (accroche, rythme, lisibilité, qualité) et évite ce qui est sanctionné. Les règles évoluent : relire les pages officielles avant de publier (Règles de la communauté TikTok, Règles YouTube sur le contenu réutilisé/inauthentique et sur le contenu synthétique, Règles Instagram).

## 1. Droits et originalité (le plus important)

- Ne republier que du contenu **à toi** ou pour lequel tu as une **autorisation écrite** / une licence.
- Un doublage ou une traduction d'une vidéo qui n'est pas la tienne n'est pas, à lui seul, une transformation suffisante : reposter le contenu d'autrui sans valeur ajoutée est limité en portée et exclu de la monétisation sur plusieurs plateformes.
- Si tu as l'accord de l'auteur, le dire en description (crédit) renforce la confiance.
- Musique : uniquement des pistes libres de droits ou de la bibliothèque de la plateforme.

## 2. Contenu synthétique (voix off IA)

- Une voix de synthèse remplace la voix d'origine : **activer l'étiquette « contenu généré/modifié par IA »** quand la plateforme l'exige (TikTok et YouTube demandent de signaler le contenu réaliste généré ou modifié par IA). En cas de doute, l'activer.
- Ne jamais imiter la voix ou le visage d'une personne réelle pour lui faire dire ce qu'elle n'a pas dit. Ne pas tromper le public sur ce qui est réel.
- Les sous-titres traduits doivent rester fidèles au sens (relire la traduction, surtout chiffres, noms, promesses).

## 3. Ce qui aide vraiment la rétention (légitime)

| Levier | Comment le skill aide |
|---|---|
| Accroche dans les 1-3 premières secondes | `highlights.py` favorise les ouvertures fortes ; Claude ajuste `start` sur la phrase d'accroche |
| Rythme sans temps mort | `--tighten` retire les blancs entre les mots (jump-cuts), `edit.py punch` pour des zooms d'emphase |
| Lisible sans le son | sous-titres mot par mot (`--style pop`), zone sûre respectée |
| Qualité image/son | 1080p, loudnorm -14 LUFS |
| Cadrage vertical net | suivi du visage, ou fond flou pour les plans larges |
| Miniature | `.jpg` choisi (image nette avec visage) pour YouTube/Reels |
| Plusieurs essais | 5 clips par vidéo, versions voix F/M (`--voice-gender both`) à comparer sur la durée de visionnage |

## 4. À éviter (risque de sanction ou de portée réduite)

- Fausses promesses, titres trompeurs, « clickbait » qui ne correspond pas au contenu.
- Incitation artificielle à l'engagement (« like sinon… »), achat de vues/abonnés, comptes multiples qui se répondent.
- Vidéos publiées avec le filigrane d'une autre plateforme (publier le fichier propre).
- Contenu dangereux, haineux, trompeur sur la santé/la finance/la politique.
- Spammer le même clip sur de nombreux comptes.

## 5. Checklist avant publication

1. Droits OK ? Auteur crédité si besoin.
2. Étiquette IA activée (voix de synthèse) ?
3. Traduction relue ? Chiffres et noms exacts ?
4. Titre ≤ 60 caractères, honnête ; description claire ; 3-5 hashtags pertinents.
5. Premières secondes regardées : donnent-elles envie de rester ?
6. Sous-titres visibles (pas masqués par l'interface), son net.
7. Durée dans les limites actuelles de la plateforme (vérifier : elles changent).
8. Après 24-48 h : regarder la **durée moyenne de visionnage** et le taux de rétention, garder ce qui marche, refaire ce qui décroche.

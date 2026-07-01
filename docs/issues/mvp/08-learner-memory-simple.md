## Objectif
Ajouter une memoire apprenant simple pour personnaliser les futures conversations.

## Contexte
Le profil stocke deja interets et objectif, et le prompt les utilise. Le MVP doit commencer a retenir des elements simples issus des sessions passees.

## Perimetre
- Stocker un resume court des dernieres conversations ou erreurs recurrentes.
- Injecter cette memoire dans le prompt de conversation.
- Mettre a jour la memoire apres generation du debrief.
- Garder un modele simple : JSON dans profil ou table dediee minimale.

## Respect architecture
- Pas de vector database pour le MVP.
- Pas de logique memoire dans les routers.
- Service/repository responsables de la persistance.

## Criteres d'acceptation
- Une information issue d'une session peut influencer une session suivante.
- La memoire reste bornee et lisible.
- Les tests prouvent l'injection dans le prompt.

## Verification
- Tests unitaires service memoire/prompt.
- Tests API si nouveau endpoint ou nouveau champ.

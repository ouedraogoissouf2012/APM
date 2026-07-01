## Objectif
Rendre le bilan de fin de session idempotent, utile et pret MVP.

## Contexte
Le debrief peut etre genere et stocke, mais l'ecran mobile appelle un POST a l'ouverture. Le MVP doit eviter les regenerations inutiles et produire un bilan vraiment exploitable.

## Perimetre
- Si un debrief existe deja pour une session, le retourner au lieu de regenerer.
- Produire resume, CEFR, 2 a 5 erreurs utiles, correction, regle en francais, type d'erreur.
- Ajouter eventuellement un conseil de prochaine session si le schema evolue.
- Garder le garde-fou anti-hallucination sur les spans originaux.

## Respect architecture
- Schema Pydantic si API change.
- Migration Alembic si modele change.
- Service debrief responsable de l'idempotence.
- Mobile model/repository mis a jour si le contrat API change.

## Criteres d'acceptation
- POST debrief est idempotent.
- GET debrief relit le bilan existant.
- Les erreurs hallucinees sont rejetees.
- Le mobile affiche le bilan sans regeneration inutile.

## Verification
- Tests unitaires analyzer/parsing.
- Tests integration API debrief.
- Tests mobile model/debrief provider.

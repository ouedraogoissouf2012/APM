## Objectif
Preparer une demo end-to-end fiable du MVP.

## Contexte
Une fois les blocs principaux stabilises, il faut pouvoir montrer le parcours sans bricolage : compte, profil, scenario, conversation, bilan, historique.

## Perimetre
- Verifier le parcours complet local.
- Documenter les commandes de lancement.
- Verifier `.env.example`.
- Lancer backend avec Postgres.
- Lancer mobile web ou emulator.
- Lancer les tests principaux.

## Respect architecture
- Pas de nouvelle feature lourde.
- Corrections uniquement si elles debloquent le parcours demo.

## Criteres d'acceptation
- Register/login fonctionne.
- Profil fonctionne.
- Scenario -> conversation -> debrief fonctionne.
- Historique fonctionne si l'issue historique est terminee.
- Les commandes de verification sont documentees.

## Verification
- `uv run ruff check .`
- `uv run mypy app`
- `uv run pytest -q` avec Docker/Postgres actif.
- `flutter test`
- Test manuel end-to-end.

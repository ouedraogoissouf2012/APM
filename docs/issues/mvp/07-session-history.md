## Objectif
Ajouter un historique des sessions pour que l'utilisateur puisse revoir sa progression.

## Contexte
Le MVP doit donner une raison de revenir : retrouver ses sessions, leurs durees, scenarios et bilans.

## Perimetre
- Ajouter `GET /sessions` pour lister les sessions de l'utilisateur courant.
- Ajouter eventuellement `GET /sessions/{id}` pour le detail.
- Inclure date, duree, mode, scenario, CEFR estime si disponible.
- Ajouter repository/view model/screen mobile pour l'historique.

## Respect architecture
- Extension de `features/sessions` ou feature dediee si necessaire.
- Ownership utilisateur verifie cote backend.
- Pagination simple si utile, sans complexite excessive.

## Criteres d'acceptation
- Un utilisateur ne voit que ses propres sessions.
- L'historique affiche les sessions recentes.
- Le detail peut mener au debrief existant.
- Les tests couvrent ownership et format de sortie.

## Verification
- Tests API sessions.
- Tests repository/view model mobile.
- `flutter test`
- `uv run pytest tests/unit -q` et integration si Postgres actif.

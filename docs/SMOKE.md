# Smoke 10 minutes

Parcours Chrome, a faire avant une demo ou un deploy.

## Preconditions

- Docker : `apm-postgres` **healthy**, port hote **6544**
- Backend : `uv run uvicorn app.main:app --reload --port 8010`
- App : `flutter run -d chrome` (API `http://localhost:8010`)

## Parcours

1. Register (email valide, mot de passe >= 8 caracteres)
2. Skip placement
3. Conversation libre : 2 tours orbe
4. **Terminer** -> bilan
5. Paires minimales : un item
6. Carnet de vocabulaire : ouvrir
7. Logout
8. Login avec le meme compte

## Notes

- 2e tap orbe = **envoyer** (Chrome), pas tuer la boucle
- 409 = ecran **Reprendre** / **Terminer et recommencer** (pas de reprise
  silencieuse en conversation libre)
- Mission / scenario : l'ancienne session est fermee puis la nouvelle
  demarre toute seule

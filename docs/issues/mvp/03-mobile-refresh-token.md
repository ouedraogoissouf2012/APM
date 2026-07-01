## Objectif
Ajouter le refresh automatique des tokens cote mobile pour eviter les deconnexions inutiles.

## Contexte
Le backend expose deja `/auth/refresh` et stocke des refresh tokens hashes et rotatifs. Le mobile sauvegarde access + refresh tokens, mais ne tente pas encore de refresh automatique quand l'access token expire.

## Perimetre
- Ajouter une methode refresh dans `AuthRepository`.
- Centraliser le comportement autant que possible pour eviter la duplication dans chaque repository.
- En cas de refresh reussi, sauvegarder les nouveaux tokens.
- En cas de refresh echoue, nettoyer les tokens et revenir a l'etat deconnecte.

## Respect architecture
- Pas de logique refresh dans les widgets.
- Pas de logique metier dans `ApiClient` si cela force un couplage trop fort avec `AuthRepository`.
- Garder `TokenStorage` comme abstraction de stockage.

## Criteres d'acceptation
- Un 401 sur une requete authentifiee peut declencher un refresh.
- Les nouveaux tokens sont persistes.
- Si le refresh echoue, l'utilisateur est deconnecte proprement.
- Les tests couvrent refresh reussi et refresh echoue.

## Verification
- `flutter test`

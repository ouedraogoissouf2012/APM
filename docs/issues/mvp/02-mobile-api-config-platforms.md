## Objectif
Rendre la configuration API mobile fiable selon la plateforme de developpement.

## Contexte
`AppConfig.dev` utilise actuellement `http://localhost:8000`. Cela fonctionne sur web/desktop local, mais pas toujours sur Android emulator, qui doit joindre la machine hote via `10.0.2.2`.

## Perimetre
- Adapter `mobile/lib/src/core/config/app_config.dart`.
- Prevoir une valeur correcte pour web/desktop et Android emulator.
- Garder une structure simple, testable et sans logique reseau dans l'UI.
- Documenter le comportement dans le README si necessaire.

## Respect architecture
- La configuration reste dans `core/config`.
- Les repositories continuent de recevoir `ApiClient`.
- Aucun endpoint backend ne change.

## Criteres d'acceptation
- L'app utilise `localhost` sur web/desktop.
- L'app utilise une URL compatible Android emulator.
- Les tests existants continuent de passer.

## Verification
- `flutter test`
- Test manuel web ou emulator si disponible.

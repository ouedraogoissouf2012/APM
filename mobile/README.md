# APM Mobile

Application Flutter du MVP Anglais Pour Moi.

## Lancement

Depuis `mobile/` :

```bash
flutter pub get
flutter run
```

Le backend doit tourner sur le port `8000`.

- Web, desktop et iOS simulator : `http://localhost:8000`
- Android emulator : `http://10.0.2.2:8000`

Cette selection est centralisee dans `lib/src/core/config/app_config.dart`.

## Tests

```bash
flutter test
```

## Stockage des tokens

L'application utilise `flutter_secure_storage` via `SecureTokenStorage`.

- Android/iOS/macOS/Windows/Linux : stockage natif sécurisé fourni par la plateforme.
- Web : le plugin s'appuie sur les mécanismes du navigateur. Ce stockage dépend du contexte web, donc l'application garde les access tokens courts côté backend, fait une rotation du refresh token, purge les tokens dès qu'un refresh échoue et purge toujours au logout.

Les tokens ne doivent jamais être loggés ni affichés dans les erreurs. Les objets d'erreur et de tokens masquent les valeurs sensibles dans `toString()`.

## Parcours couvert

- login/register ;
- profil apprenant ;
- choix de scenario ;
- conversation tour-par-tour avec STT/TTS du device ;
- refresh automatique des tokens ;
- bilan de session ;
- historique des sessions.

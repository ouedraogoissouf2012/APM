# APM Mobile

Application Flutter du MVP Anglais Pour Moi.

## Lancement

Depuis `mobile/` :

```bash
flutter pub get
flutter run
```

Le backend local doit tourner sur le port `8010`
(`uv run uvicorn app.main:app --reload --port 8010`).
L'image Docker de l'API reste mappee `8000:8000`.

- Web, desktop et iOS simulator : `http://localhost:8010`
- Android emulator : `http://10.0.2.2:8010`

Cette selection est centralisee dans `lib/src/core/config/app_config.dart`.

Web/PWA = **beta** (micro navigateur + tokens XSS, #495). Produit = Play
Store : [`docs/ANDROID-PLAY.md`](../docs/ANDROID-PLAY.md).

## Tests

```bash
flutter test
```

## Stockage des tokens

L'application utilise `flutter_secure_storage` via `SecureTokenStorage`.

- Android/iOS/macOS/Windows/Linux : Keystore / Keychain.
- Web (beta, #495) : la clé AES du plugin est dans `localStorage`. XSS ou
  DevTools lisent la session. Chrome = canal de **dev**, pas un produit
  sécurisé. Access tokens courts, rotation du refresh, purge au refresh
  raté et au logout.

Les tokens ne doivent jamais être loggés ni affichés dans les erreurs. Les objets d'erreur et de tokens masquent les valeurs sensibles dans `toString()`.

## Parcours couvert

- login/register ;
- profil apprenant ;
- choix de scenario ;
- conversation tour-par-tour avec STT/TTS du device ;
- refresh automatique des tokens ;
- bilan de session ;
- historique des sessions.

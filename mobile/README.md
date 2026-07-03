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

## Parcours couvert

- login/register ;
- profil apprenant ;
- choix de scenario ;
- conversation tour-par-tour avec STT/TTS du device ;
- refresh automatique des tokens ;
- bilan de session ;
- historique des sessions.

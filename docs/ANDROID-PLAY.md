# Android Play Store (#505)

Chrome = canal de **dev**. Produit consommable = **Play Store** d'abord, iOS
ensuite. Le web/PWA est **beta** : micro navigateur + tokens en
`localStorage` (XSS, #495).

## Build AAB

Depuis `mobile/` :

```bash
flutter build appbundle
```

Play attend un `.aab`, pas un APK. `versionCode` vient du `+N` dans
`pubspec.yaml` (`1.0.0+1` → code 1). Incrementer `+N` a chaque upload.

## Signature

`android/key.properties` et `*.jks` / `*.keystore` sont gitignores.

Si `android/key.properties` existe, le build release le signe. Sinon, debug
keys (dev seulement, `flutter run --release`).

Exemple `android/key.properties` :

```
storePassword=...
keyPassword=...
keyAlias=upload
storeFile=upload-keystore.jks
```

Ne jamais committer le keystore.

## Hors repo

Compte Play Console, fiche (nom, graphic, screenshots, Data safety micro),
politique de confidentialite (audio = donnee perso), review Google.

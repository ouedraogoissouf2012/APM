# Dépendances mobile — justification

Règle : chaque package externe est listé et justifié ici. Toute nouvelle
dépendance doit ajouter sa ligne (et la revue de PR doit la challenger).

## Dépendances de production

| Package | Rôle | Justification |
|---|---|---|
| `flutter_riverpod` | Gestion d'état (MVVM) | Injection de dépendances + état réactif testable ; standard du projet (view models par feature, fakes en tests). API manuelle sans codegen (conflits analyzer documentés). |
| `go_router` | Navigation déclarative | Routing centralisé dans `core/router/`, redirect auth piloté par l'état ; package officiel Flutter. |
| `dio` | Client HTTP | Intercepteurs (auth/refresh token), timeouts, erreurs typées — au-delà de `http`. Abstrait derrière `ApiClient` (`core/network/`), les repositories ne voient jamais Dio. |
| `flutter_secure_storage` | Stockage des tokens | Keychain/Keystore natifs pour les JWT — jamais de secrets en clair. Abstrait derrière `TokenStorage`. |
| `speech_to_text` | STT sur l'appareil | Cœur du MVP voix tour-par-tour : reconnaissance gratuite sur le device, pas de clé API. Abstrait derrière `SpeechService`. |
| `flutter_tts` | TTS sur l'appareil | Lecture des réponses de l'IA sans service payant. Abstrait derrière `SpeechService`. |
| `cupertino_icons` | Icônes iOS | Standard Flutter. |

## Polices (assets, pas des packages)

Fraunces et Inter (DESIGN_SPEC §3) sont **bundlées** dans
`assets/fonts/` (licence SIL OFL, incluse et enregistrée dans le
`LicenseRegistry` au démarrage).

**Décision** : `google_fonts` a été volontairement écarté. Il télécharge
les polices au runtime : premier lancement hors-ligne = polices système,
tests non déterministes (HTTP bloqué), dépendance CDN. Le bundle local
garantit le rendu de marque partout, tout le temps. C'est une déviation
assumée du DESIGN_SPEC (qui prescrivait le *moyen* `google_fonts`, pas
la fin).

## Dépendances de développement

| Package | Rôle | Justification |
|---|---|---|
| `flutter_test` | Tests | SDK. |
| `flutter_lints` | Analyse statique | Règles officielles ; `flutter analyze` doit rester à zéro. |
| `mocktail` | Mocks/fakes | Doubles de test sans codegen, cohérent avec l'interdiction de build_runner dans ce projet. |

## Principes

- Un service externe = une interface abstraite dans `core/` ; les
  implémentations concrètes sont injectées via Riverpod. Les features ne
  dépendent jamais d'un package directement.
- Pas de package pour ce qu'on peut écrire simplement (ex. le design
  system est 100 % maison — pas de kit UI tiers, l'identité visuelle est
  un différenciateur).

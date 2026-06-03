# ADR — Alignement architecture 2026 (feature-first backend + MVVM Flutter)

**Date :** 2026-06-03
**Statut :** Accepté
**Contexte :** Recherche des tendances d'architecture 2026 pour nos deux langages, objectif « simple à maintenir ». Issue GitHub #31.

---

## Décision 1 — Backend FastAPI : feature-first (vertical slices)

On réorganise le backend **par domaine** (feature-first), pas par couche technique.

**Pourquoi :** la référence communautaire (`zhanymkanov/fastapi-best-practices`) et les sources 2025-2026 (PyCon India, Leapcell/Vertical Slice Architecture) convergent : grouper par domaine réduit la charge cognitive (tout le code d'une fonctionnalité au même endroit) et le couplage entre domaines. Le layer-first (`api/`, `services/`, `repositories/`…) ne passe pas l'échelle dès plusieurs domaines.

**Structure :**
```
app/
  main.py, config.py, database.py, registry.py   # racine
  core/        security, livekit, quota, rate_limit, logging   # cross-cutting partagé
  domain/      exceptions.py                                   # exceptions métier partagées
  api/         errors.py, middleware.py                        # préoccupations web transverses
  features/
    auth/      router · service · repository · models · schemas · dependencies
    profile/   (idem)
    sessions/  (idem)
```

**On garde la couche repository** (à contre-courant de la majorité « SQLAlchemy suffit ») car elle est **justifiée par les tests unitaires sans base via des fakes** (Liskov), exigence explicite du projet. Le débat repository-sur-SQLAlchemy n'a pas de consensus communautaire ; notre choix est assumé et documenté. On n'ajoute PAS de cérémonie supplémentaire (pas de Clean Architecture complète, pas de use-cases) tant qu'un besoin concret ne l'exige pas.

**DI** : `Depends` natif de FastAPI (suffisant pour une petite équipe ; pas de conteneur DI).

## Décision 2 — App mobile Flutter : architecture officielle MVVM + Riverpod 3

Pour le sous-projet 6, on adopte l'**architecture officielle Flutter** (docs.flutter.dev/app-architecture, app de référence « Compass ») :
- **MVVM + Repository**, structure **hybride Compass** : `ui/` par feature (1 View + 1 ViewModel), `data/` par type (`repositories/` + `services/`).
- **State management : Riverpod 3.0 + codegen** (`@riverpod`, `Notifier`/`AsyncNotifier`/`StreamNotifier`) — défaut 2026, sert aussi de DI. (BLoC reste une alternative valable, surtout pour la machine à états de la connexion vocale.)
- `freezed` (modèles + états immuables, états scellés `Connecting/Listening/Speaking/Error`), `go_router`.
- **Pas de Clean Architecture complète, pas de use-cases** par défaut (la doc officielle les juge superflus dans la plupart des apps).
- **Voix temps réel** : `VoiceService` (wrappe `livekit_client`/`flutter_webrtc` → `Stream`s) → `ConversationRepository` (source de vérité, reconnexion) → `ViewModel`.

## Alternatives écartées
- **Backend layer-first** (l'actuel) : OK pour un seul domaine, friction dès plusieurs ; écarté.
- **Supprimer le repository** (version minimaliste 2026) : perdrait les tests unitaires avec fakes voulus ; écarté.
- **Clean Architecture / use-cases (back et front)** : sur-ingénierie pour la taille actuelle ; écarté (la doc Flutter officielle le dit elle-même).

## Ce qui me ferait revoir
Si la logique restait du CRUD pur (repository = cérémonie) — ce n'est pas le cas (quota atomique, durée serveur, CEFR, bilan async). Côté Flutter, si l'équipe avait déjà une forte expertise BLoC, on basculerait le state management sans changer la structure.

## Sources clés
- https://github.com/zhanymkanov/fastapi-best-practices
- https://docs.flutter.dev/app-architecture/guide · /recommendations · /case-study
- https://riverpod.dev/docs/whats_new (Riverpod 3.0)

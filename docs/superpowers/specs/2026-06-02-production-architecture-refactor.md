# ADR — Architecture de production du backend APM

**Date :** 2026-06-02
**Statut :** Accepté
**Contexte :** Suite à la revue honnête du socle MVP (voir mémoire `backend-foundation-known-gaps`), refonte vers une architecture professionnelle de production. Epic GitHub #16.

---

## 1. Problème

Le socle MVP mélange HTTP + métier + persistance dans les routes (viole SRP/DIP), fait confiance à des données client (durée de session), a une race sur le quota, et n'a ni interfaces (donc LSP non exercé), ni gestion d'erreurs/logging, ni outillage qualité. Voir la revue pour le détail chiffré.

## 2. Décision : architecture en couches (hexagonale allégée)

Quatre couches, dépendances dirigées **vers l'intérieur** (le métier ne dépend de rien d'infrastructurel) :

```
┌────────────────────────────────────────────────────────┐
│  API (FastAPI)         app/api/                          │
│  routes = HTTP seul · DTOs (schemas) · deps (injection)  │
│  + handlers d'exception centralisés                      │
└───────────────┬──────────────────────────────────────────┘
                │ dépend de (interfaces)
┌───────────────▼──────────────────────────────────────────┐
│  SERVICES              app/services/                      │
│  logique métier / cas d'usage · PAS de FastAPI, PAS de SQL│
│  lève des exceptions de DOMAINE                           │
└───────────────┬──────────────────────────────────────────┘
                │ dépend de (Protocol)
┌───────────────▼──────────────────────────────────────────┐
│  REPOSITORIES          app/repositories/                  │
│  Protocol (interface) + implémentation SQLAlchemy         │
│  seul endroit qui connaît l'ORM                           │
└───────────────┬──────────────────────────────────────────┘
                │ manipule
┌───────────────▼──────────────────────────────────────────┐
│  DOMAIN / INFRA        app/domain/  app/models/  app/core/│
│  exceptions & règles pures · modèles ORM · sécurité/config│
└────────────────────────────────────────────────────────┘
```

### Pourquoi cette architecture sert les principes SOLID

- **SRP** : une route ne fait que de l'HTTP ; un service ne fait que du métier ; un repository ne fait que de la persistance.
- **DIP** : les services dépendent d'**interfaces de repository** (`typing.Protocol`), pas de SQLAlchemy concret. L'implémentation concrète est **injectée** via les dépendances FastAPI.
- **LSP** : grâce aux Protocols de repository, on peut substituer une implémentation SQLAlchemy par un **fake en mémoire** dans les tests unitaires — sans changer le service. C'est exactement le contrat substituable de Liskov, et ça rend les services **testables unitairement** (sans DB).
- **OCP** : on ajoute un nouveau fournisseur (ex. `VoiceEngine` pipeline vs S2S) en implémentant une interface, sans modifier les consommateurs.
- **ISP** : interfaces fines, une par agrégat (UserRepository, ProfileRepository, SessionRepository).

## 3. Conventions

- **Exceptions de domaine** (`app/domain/exceptions.py`) : `DomainError` et sous-classes (`EmailAlreadyExists`, `InvalidCredentials`, `QuotaExhausted`, `NotFound`...). Les services lèvent ces exceptions, **jamais** de `HTTPException`.
- **Mapping vers HTTP** centralisé (`app/api/errors.py`) : un handler par type de `DomainError` → code HTTP + corps JSON normalisé `{ "error": { "code", "message" } }`.
- **Injection** (`app/api/deps.py`) : `get_*_service()` construit le service avec le repository SQLAlchemy lié à la session de requête.
- **Unité de travail** : le service reçoit la session/`commit` via le repository ; les transactions sont gérées au niveau service (un cas d'usage = une transaction).

## 4. Correctifs intégrés à la refonte

| Faille | Correctif |
|---|---|
| Durée client (🔴) | `SessionService.end_session` calcule la durée **serveur** (`ended_at - started_at`) ; le champ client est ignoré. |
| Race quota (🔴) | Quota vérifié **et** réservé à l'ouverture, de façon atomique (transaction + `SELECT … FOR UPDATE` sur l'utilisateur) ; sessions actives comptabilisées. |
| room_name collision (🟠) | `room_name` = `apm-{user}-{uuid4}`. |
| Auth (🟠) | Access + **refresh tokens** (rotation + révocation via table `refresh_tokens`), **rate-limit** sur `/auth/login`. |
| Robustesse (🟡) | Handlers d'exception + **logging structuré** + CORS + headers. |
| Outillage (🟡) | **ruff** (lint+format), **mypy** (strict), **pre-commit**, **CI** GitHub Actions (lint+types+tests). |

## 5. Structure cible

```
backend/app/
  domain/
    __init__.py
    exceptions.py        # DomainError + sous-classes
  repositories/
    __init__.py
    user_repository.py   # UserRepository (Protocol) + SqlAlchemyUserRepository
    profile_repository.py
    session_repository.py
  services/
    __init__.py
    auth_service.py      # AuthService (register/login/authenticate)
    profile_service.py
    session_service.py
  api/
    deps.py              # get_db + get_*_service + get_current_user
    errors.py            # register_exception_handlers(app)
    routes/ (auth, profile, sessions)
  core/                  # security, livekit, config, logging
  models/                # ORM (infra)
  schemas/               # DTOs API
backend/tests/
  unit/                  # services testés avec fakes (sans DB)
    fakes.py             # InMemory*Repository (implémentent les Protocols)
    test_auth_service.py ...
  integration/           # routes + DB réelle
```

## 6. Ordre d'exécution (PRs)

1. **#17** Noyau en couches + auth refactoré (référence) + fakes + tests unitaires. ⟵ *cette PR*
2. **#18** Profil dans les couches.
3. **#19** Sessions + correctifs critiques (durée serveur, quota atomique, UUID).
4. **#20** Refresh tokens + rate-limiting.
5. **#21** Erreurs centralisées + logging + CORS.
6. **#22** Outillage qualité + CI.
7. **#23** Tests unitaires cas limites (complément transverse).

## 7. Alternatives écartées

- **Garder les routes « fat »** : rapide mais re-crée la dette ; rejeté (cf. exigence qualité).
- **Architecture hexagonale stricte (ports/adapters complets, DTO mapping partout)** : sur-ingénierie pour la taille actuelle ; on adopte une version **allégée** (Protocols + services) qui donne 90 % des bénéfices sans la cérémonie.
- **Django (ORM + admin)** : déjà écarté en spec ; FastAPI async reste adapté.

## 8. Ce qui me ferait revoir cette décision

Si la logique métier restait triviale (CRUD pur) au point que les couches n'ajoutent que de la cérémonie. Ce n'est pas le cas : quota, durée serveur, niveau CEFR adaptatif, bilan async, mémoire — autant de vraie logique métier qui justifie la séparation.

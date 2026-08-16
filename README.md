# APM - Anglais Pour Moi

APM est une application mobile d'apprentissage de l'anglais oral par IA. Le but
produit reste ambitieux : aider un apprenant francophone a parler davantage, sans
pression, puis lui donner un bilan clair de ses erreurs et de sa progression.

## MVP actuel

Le code actuel implemente un MVP pragmatique, tour-par-tour :

1. le mobile ecoute l'utilisateur avec le moteur speech-to-text du telephone ou du
   navigateur ;
2. le texte reconnu est envoye au backend via `POST /sessions/{id}/turn` ;
3. le backend appelle un LLM derriere l'interface `LlmProvider` ;
4. la reponse texte est retournee au mobile ;
5. le mobile lit la reponse avec son moteur text-to-speech ;
6. le backend conserve le transcript ;
7. a la fin, le backend genere et stocke un bilan de session.

Ce MVP ne fait donc pas encore de streaming audio temps reel via LiveKit. Il permet
de valider plus vite le coeur pedagogique : parler, recevoir une reponse, terminer
la session, obtenir un bilan.

## Vision cible

La vision long terme reste :

- conversation vocale temps reel avec LiveKit Agents ;
- pipeline STT -> LLM -> TTS cote agent vocal ;
- notation de prononciation au niveau phoneme avec Azure AI Speech ;
- bilan intelligent `faute -> regle -> bonne formulation` ;
- memoire persistante du profil, des conversations et des erreurs recurrentes ;
- niveau CEFR adaptatif ;
- scenarios guides et mode libre ;
- abonnement et quotas par utilisateur.

## Differenciateur

APM vise la combinaison suivante :

- conversation libre et profonde ;
- feedback de grammaire differe, pour ne pas casser le flux ;
- memoire persistante de l'apprenant ;
- a terme, notation de prononciation au niveau du phoneme.

Cette combinaison est l'espace produit vise par le projet.

## Stack technique

| Couche | MVP actuel | Vision cible |
|---|---|---|
| Mobile | Flutter, Riverpod, GoRouter, Dio | Flutter + client LiveKit |
| Voix | `speech_to_text` + `flutter_tts` cote mobile | LiveKit Agents / WebRTC |
| Backend | Python 3.12, FastAPI async | Idem |
| Base de donnees | PostgreSQL | PostgreSQL |
| Conversation IA | `LlmProvider` fake ou DeepSeek | Provider interchangeable, realtime premium possible |
| Bilan | LLM JSON strict, fake ou DeepSeek | LLM + validation plus robuste, ERRANT possible |
| Prononciation | Non implemente | Azure AI Speech Pronunciation Assessment |

## Fonctionnalites implementees

Backend :

- authentification email/password ;
- access token JWT court ;
- refresh token rotatif, stocke sous forme hashee ;
- rate-limit sur login ;
- profil apprenant ;
- sessions de conversation ;
- quota gratuit journalier ;
- generation de jeton LiveKit cote backend, pour la future voie realtime ;
- endpoint de conversation tour-par-tour ;
- transcript persistant ;
- generation et lecture de bilan ;
- historique des sessions recentes ;
- memoire apprenant simple alimentee par les bilans ;
- erreurs domaine centralisees ;
- migrations Alembic ;
- tests unitaires et integration.

Mobile :

- login/register ;
- stockage securise des tokens ;
- refresh automatique des access tokens expires ;
- home ;
- profil ;
- choix de scenario ;
- conversation tour-par-tour par micro ;
- text-to-speech de la reponse ;
- ecran de bilan ;
- historique des sessions ;
- tests repositories, view models et widgets.

## Limites actuelles

- Pas encore de LiveKit Agent temps reel.
- Pas encore de scoring de prononciation Azure.
- Pas encore de memoire apprenant vectorielle ou long terme avancee.
- Le mode par defaut utilise des moteurs fake pour pouvoir developper sans cle API.

## Variables d'environnement backend

Le backend lit `backend/.env`. Exemple :

```bash
DATABASE_URL=postgresql+asyncpg://apm:apm_dev_password@localhost:6544/apm
DATABASE_URL_TEST=postgresql+asyncpg://apm:apm_dev_password@localhost:6544/apm_test

JWT_SECRET=change-me-in-production-use-a-long-random-string
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30

LOGIN_RATE_LIMIT_MAX=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=60

FREE_TIER_DAILY_MINUTES=10

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
GROQ_API_KEY=
VOICE_ENGINE=fake
DEBRIEF_ENGINE=fake
STT_ENGINE=device
TTS_ENGINE=device
```

`VOICE_ENGINE=fake` garde la conversation en mode fake. Pour utiliser DeepSeek
dans le backend, renseigner `DEEPSEEK_API_KEY` puis mettre `VOICE_ENGINE=deepseek`.

`DEBRIEF_ENGINE=fake` retourne un bilan de demonstration valide. Pour un vrai
bilan LLM, renseigner `DEEPSEEK_API_KEY` puis mettre `DEBRIEF_ENGINE=deepseek`.

L'image API : `docker compose --profile app up --build` (postgres + redis + backend).
En staging/production, `APP_ENV=production` est obligatoire (sinon `/docs`, CORS `*`, JWT exemple).

## Lancer le projet en local

### 1. Base de donnees

Depuis la racine du repo :

```bash
docker compose up -d postgres
```

Le service PostgreSQL ecoute sur le port hote `6544` (5432 = PostgreSQL local,
5433 = autre projet ; et la plage 5433-5532 est reservee par Windows/WinNAT, ou
Docker ne peut pas se lier — d'ou 6544). `backend/.env` doit utiliser ce meme port.

### 2. Backend

Depuis `backend/` :

```bash
uv sync
copy .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Verification :

```bash
curl http://127.0.0.1:8000/health
```

La documentation OpenAPI est disponible sur :

```text
http://127.0.0.1:8000/docs
```

### 3. Mobile

Depuis `mobile/` :

```bash
flutter pub get
flutter run
```

En developpement web/desktop/iOS simulator, l'API pointe vers
`http://localhost:8000`. Sur Android emulator, l'app utilise
`http://10.0.2.2:8000` pour joindre la machine hote.

## Verification

Backend :

```bash
cd backend
uv run ruff check .
uv run mypy app
uv run pytest tests/unit -q
```

La suite complete `uv run pytest -q` necessite PostgreSQL actif via Docker.

Mobile :

```bash
cd mobile
flutter test
```

## Demo MVP locale

Checklist avant demo :

1. Demarrer PostgreSQL :

```bash
docker compose up -d postgres
```

2. Preparer et lancer le backend :

```bash
cd backend
copy .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

3. Verifier le backend :

```bash
curl http://127.0.0.1:8000/health
```

4. Lancer le mobile :

```bash
cd mobile
flutter run
```

Parcours a montrer :

- creer un compte ou se connecter ;
- ouvrir le profil, saisir quelques interets et un objectif ;
- choisir un scenario ;
- demarrer une conversation, parler, ecouter la reponse ;
- terminer la session ;
- consulter le bilan ;
- revenir a l'accueil et ouvrir l'historique ;
- ouvrir un ancien bilan depuis l'historique quand un CEFR est disponible.

## Documentation projet

- Spec de conception :
  [`docs/superpowers/specs/2026-06-02-app-anglais-oral-design.md`](docs/superpowers/specs/2026-06-02-app-anglais-oral-design.md)
- Plan backend foundation :
  [`docs/superpowers/plans/2026-06-02-backend-foundation.md`](docs/superpowers/plans/2026-06-02-backend-foundation.md)
- Issues MVP locales :
  [`docs/issues/mvp`](docs/issues/mvp)

## Workflow de developpement

- Chaque fonctionnalite doit partir d'une issue GitHub.
- Chaque changement important passe par une branche dediee.
- Les routers restent fins.
- La logique metier vit dans les services.
- La persistance passe par les repositories.
- Les schemas API restent explicites.
- Les tests accompagnent les changements de comportement.

## Ordre MVP recommande

1. MVP 01 - Aligner la documentation sur le MVP actuel.
2. MVP 02 - Rendre la config API mobile fiable par plateforme.
3. MVP 03 - Ajouter le refresh token automatique cote mobile.
4. MVP 04 - Stabiliser DeepSeek pour conversation et bilan.
5. MVP 05 - Ameliorer l'experience de conversation MVP.
6. MVP 06 - Rendre le debrief idempotent et utile.
7. MVP 07 - Ajouter l'historique des sessions.
8. MVP 08 - Ajouter une memoire apprenant simple.
9. MVP 09 - Preparer une demo end-to-end fiable.

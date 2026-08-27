# 🚀 Lancer APM — guide pas à pas

Ce guide te fait démarrer **APM** en local, de zéro jusqu'à parler à l'IA
dans l'application. Suis les étapes dans l'ordre.

> **Ce dont tu as besoin une fois** : Docker Desktop, Flutter SDK, `uv`
> (gestionnaire Python), et un navigateur Chrome. Voir §6 si l'un manque.

---

## Vue d'ensemble : 3 briques

APM = **3 processus qui tournent en même temps** :

| Brique | Rôle | Port |
|---|---|---|
| 🐘 **PostgreSQL** (Docker) | Base de données | `6544` |
| 🐍 **Backend** (FastAPI) | API, IA texte, quotas | `8010` |
| 📱 **App mobile** (Flutter) | L'interface | Chrome ou émulateur |

Il faut les lancer **dans cet ordre** : base → backend → app.

---

## 1. Démarrer la base de données

Ouvre **Docker Desktop** et attends qu'il soit prêt. Puis, depuis la racine
du projet (`anglais pour moi/`) :

```bash
docker compose up -d postgres
```

Vérifie qu'elle tourne :

```bash
docker ps
```

Tu dois voir une ligne `apm-postgres` avec le statut `healthy` ou `Up`.

> 💡 PostgreSQL écoute sur le port hôte **6544** (5432 = PostgreSQL local ;
> 5433–5532 est réservé par Windows WinNAT, Docker ne peut pas s'y lier).

---

## 2. Démarrer le backend

Ouvre un **nouveau terminal**, va dans `backend/`, et la première fois
seulement, prépare l'environnement :

```bash
cd backend
uv sync                          # installe les dépendances (1re fois)
copy .env.example .env           # crée ta config locale (1re fois)
uv run alembic upgrade head      # crée les tables (1re fois)
```

Puis, **à chaque lancement** :

```bash
uv run uvicorn app.main:app --reload --port 8010
```

Laisse ce terminal ouvert. Vérifie dans un autre terminal :

```bash
curl http://127.0.0.1:8010/health
```

Réponse attendue : `{"status":"ok"}`.
La doc interactive de l'API est sur <http://127.0.0.1:8010/docs>.

---

## 3. Démarrer l'application

Ouvre un **troisième terminal**, va dans `mobile/`, et la première fois :

```bash
cd mobile
flutter pub get                  # installe les paquets (1re fois)
```

Puis lance l'app :

### Option A — dans le navigateur (le plus simple)

```bash
flutter run -d chrome
```

Une fenêtre Chrome s'ouvre avec APM. **C'est la façon la plus rapide de
voir l'app.**

### Option B — sur un émulateur Android

Lance d'abord ton émulateur depuis Android Studio (ou
`flutter emulators --launch <nom>`), puis :

```bash
flutter run
```

> Sur émulateur Android, l'app joint le backend via `10.0.2.2:8010`
> automatiquement — rien à configurer.

---

## 4. Utiliser l'application (parcours complet)

1. **Crée un compte** : email valide + mot de passe d'**au moins 8
   caractères** (ex. `test@apm.dev` / `motdepasse123`).
2. **Profil** : renseigne quelques centres d'intérêt et ton objectif.
3. **Choisis un scénario** (restaurant, entretien, small talk…) ou le
   mode libre.
4. **Conversation** : touche l'orbe, autorise le micro, **parle en
   anglais**. L'IA répond à voix haute, et l'écoute enchaîne toute seule.
5. **Termine** la session (icône raccrocher) → tu arrives sur le **bilan**
   (niveau CEFR, ce qui a marché, corrections).
6. **Historique** : retrouve tes anciennes sessions depuis l'accueil.

---

## 5. Mode démo vs. vraie IA

Par défaut, le backend tourne en **mode fake** (aucune clé API requise) :
les réponses de l'IA et le bilan sont des démonstrations valides. Parfait
pour tester le parcours sans frais.

**Pour activer la vraie IA**, édite `backend/.env` :

```bash
GROQ_API_KEY=ta-cle-groq-ici
VOICE_ENGINE=groq
DEEPSEEK_API_KEY=ta-cle-deepseek-ici
DEBRIEF_ENGINE=deepseek
```

Groq (Llama) pour le tour parlé (~0.4 s). DeepSeek pour le bilan / missions.

Puis **redémarre le backend** (Ctrl+C dans son terminal, puis relance la
commande `uvicorn` de l'étape 2).

> La reconnaissance vocale (micro) et la synthèse (voix) tournent **sur
> l'appareil** — gratuites, aucune clé nécessaire.

---

## 6. Prérequis — installer ce qui manque

| Outil | Vérifier | Installer |
|---|---|---|
| Docker Desktop | `docker --version` | <https://docker.com/products/docker-desktop> |
| Flutter | `flutter --version` | <https://docs.flutter.dev/get-started/install> |
| uv | `uv --version` | `pip install uv` |

Un diagnostic Flutter complet : `flutter doctor`.

---

## 7. En cas de problème

| Symptôme | Cause probable | Solution |
|---|---|---|
| `curl /health` échoue | Backend pas démarré, ou Docker éteint | Refais §1 puis §2 |
| Inscription refusée (422) | Mot de passe < 8 caractères | Utilise 8 caractères minimum |
| « Trop de tentatives » | Rate-limit (5 essais/min) | Attends ~1 minute |
| Port 8010 déjà utilisé | Un autre projet occupe le port | Ferme-le, ou lance sur `--port 8011` (+ `--dart-define=API_BASE_URL=http://localhost:8011` côté Flutter) |
| « Rien ne se passe » quand je parle | Micro non autorisé, ou mauvais micro sélectionné | Autorise le micro dans le navigateur ; vérifie le micro par défaut de Windows |
| Ton temps gratuit est terminé | Quota de 10 min/jour atteint | Reviens demain, ou augmente `FREE_TIER_DAILY_MINUTES` dans `.env` (dev uniquement) puis redémarre le backend |
| L'émulateur ne démarre pas | RAM insuffisante | Ferme des applis, ou baisse `hw.ramSize` de l'AVD ; sinon utilise Chrome |
| La base refuse la connexion | Conteneur arrêté | `docker start apm-postgres` |

---

## 8. Tout arrêter

- **App** : `Ctrl+C` dans le terminal Flutter.
- **Backend** : `Ctrl+C` dans son terminal.
- **Base** (optionnel, les données sont conservées) :
  ```bash
  docker compose stop postgres
  ```

---

## Aide-mémoire (une fois tout installé)

Trois terminaux, dans l'ordre :

```bash
# Terminal 1 — base (depuis la racine)
docker compose up -d postgres

# Terminal 2 — backend (depuis backend/)
uv run uvicorn app.main:app --reload --port 8010

# Terminal 3 — app (depuis mobile/)
flutter run -d chrome
```

Bonne pratique ! 🎧

---

## Variante : tout lancer avec Docker (`--profile app`)

Postgres + Redis + API dans Compose (l'API écoute alors sur **8000**,
pas 8010) :

```bash
docker compose --profile app up --build
```

Vérifie :

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/ready
```

`GET /health/ready` est la probe à brancher sur le load balancer.
Détail opérateur : [`DEPLOY.md`](DEPLOY.md).

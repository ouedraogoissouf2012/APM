# Deploy production

Checklist operateur. Le fail-fast vit deja dans
`Settings.validate_production_safety` (`backend/app/config.py`) : une
instance staging/production refuse de demarrer si un garde est viole.

## Variables obligatoires

- `APP_ENV=production` (ou `staging` : memes gardes)
- `JWT_SECRET` >= 32 octets, pas l'exemple du repo
  (`change-me-in-production-use-a-long-random-string`)
- `CORS_ALLOW_ORIGINS` sans `*` si `CORS_ALLOW_CREDENTIALS` est actif
- `REDIS_URL` (rate-limit et cache TTS partages entre workers)
- cles LLM selon `VOICE_ENGINE` / `DEBRIEF_ENGINE` / `MISSION_ENGINE` /
  `SHADOWING_ENGINE` :
  - DeepSeek ou `groq_fallback` -> `DEEPSEEK_API_KEY`
  - Groq ou `groq_fallback` -> `GROQ_API_KEY`
- si `PRONUNCIATION_ENGINE=gop` : `GOP_SERVICE_URL` + `GOP_SERVICE_SECRET`
- `EXPOSE_RESET_TOKEN` interdit en staging/production
- optionnel : `ALERT_WEBHOOK_URL` (Discord/Slack) pour 5xx et `meter_failures`

## Probes

Brancher le load balancer sur **readiness**, pas sur liveness :

- liveness : `GET /health` (le process repond)
- readiness : `GET /health/ready` (postgres + redis joignables)

Exemple : `curl http://127.0.0.1:8000/health/ready`

## Image API

`docker compose --profile app up --build` publie l'API sur `8000:8000`
(postgres + redis + backend). Ne pas confondre avec le run local uvicorn
sur le port **8010**.

## Hors scope ici

`docs/LAUNCH-READINESS.md` est perime (ports, comptes de tests, Azure).
Ne pas s'en servir comme runbook.

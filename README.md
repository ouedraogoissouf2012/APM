# APM — Anglais Pour Moi

Application mobile d'apprentissage de l'**anglais oral** par IA : une vraie conversation parlée en temps réel avec une IA, sans pression, qui remet à la fin un **bilan des erreurs** (faute → règle → bonne formulation) dans la langue maternelle, plus un **score de prononciation par phonème**.

## Différenciateur

Personne ne combine aujourd'hui : notation prononciation au niveau du **phonème** + conversation **libre profonde** + **mémoire persistante** du profil et des conversations. APM occupe cet espace laissé vide par les leaders du marché.

## Stack technique

| Couche | Choix |
|---|---|
| Mobile | Flutter (Dart) |
| Backend | Python / FastAPI (async) |
| Base de données | PostgreSQL |
| Voix temps réel | LiveKit Agents (pipeline STT→LLM→TTS ; OpenAI gpt-realtime en premium) |
| Prononciation | Azure AI Speech — Pronunciation Assessment |
| Bilan grammaire | LLM (JSON strict) + ERRANT (validation/typage), async |
| Fluidité | CrisperWhisper |

## Documentation

- **Spec de conception** : [`docs/superpowers/specs/2026-06-02-app-anglais-oral-design.md`](docs/superpowers/specs/2026-06-02-app-anglais-oral-design.md)
- **Plan d'implémentation (fondation backend)** : [`docs/superpowers/plans/2026-06-02-backend-foundation.md`](docs/superpowers/plans/2026-06-02-backend-foundation.md)

## Périmètre MVP

Conversation vocale temps réel · mémoire persistante · bilan d'erreurs intelligent · niveau CEFR adaptatif · scoring prononciation par phonème · scénarios guidés + mode libre.

## Workflow de développement

- Chaque **fonctionnalité** a une **issue** GitHub.
- Chaque action de code passe par une **branche** dédiée et une **Pull Request** liée à son issue.
- TDD : tests d'abord, commits fréquents.

## Sous-projets (ordre de construction)

1. Fondation backend (auth, sessions, quotas, jetons LiveKit)
2. Agent vocal temps réel
3. Service bilan (grammaire + CEFR)
4. Service prononciation (Azure)
5. Mémoire & CEFR adaptatif
6. App mobile Flutter
7. Billing & abonnements

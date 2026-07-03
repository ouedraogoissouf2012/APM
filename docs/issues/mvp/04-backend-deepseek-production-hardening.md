## Objectif
Stabiliser l'usage reel de DeepSeek pour la conversation et le bilan.

## Contexte
Le provider DeepSeek existe deja derriere l'interface `LlmProvider`, mais le mode par defaut reste fake. Le MVP doit pouvoir passer a `VOICE_ENGINE=deepseek` et `DEBRIEF_ENGINE=deepseek` avec une gestion d'erreurs propre.

## Perimetre
- Verifier/renforcer `DeepSeekLlmProvider`.
- Ajouter une exception domaine adaptee en cas d'echec LLM si necessaire.
- Mapper l'erreur en HTTP proprement.
- Verifier que conversation et debrief utilisent le provider sans appel direct depuis les routers.
- Documenter les variables d'environnement.

## Respect architecture
- Les routers restent fins.
- Les services dependent de `LlmProvider`.
- Aucun appel API externe directement depuis les widgets ou routers.

## Criteres d'acceptation
- `VOICE_ENGINE=deepseek` active la conversation reelle.
- `DEBRIEF_ENGINE=deepseek` active le bilan reel.
- Une erreur provider retourne une reponse API normalisee.
- Les tests unitaires n'appellent jamais le reseau.

## Verification
- `uv run pytest tests/unit -q`
- `uv run ruff check .`
- `uv run mypy app`
- Smoke test manuel avec cle DeepSeek.

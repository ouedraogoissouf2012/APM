## Objectif
Mettre la documentation en coherence avec l'etat reel du code : MVP tour-par-tour avec STT/TTS cote mobile, backend LLM texte, transcript et bilan.

## Contexte
La vision long terme mentionne LiveKit/Azure, mais le code actuel utilise une approche pragmatique : mobile speech-to-text/text-to-speech -> backend `/sessions/{id}/turn` -> transcript -> debrief.

## Perimetre
- Mettre a jour `README.md` avec une section `MVP actuel` et une section `Vision future`.
- Documenter le lancement backend/mobile/Postgres.
- Clarifier `VOICE_ENGINE`, `DEBRIEF_ENGINE`, `DEEPSEEK_API_KEY`.
- Documenter les limites actuelles : pas encore LiveKit temps reel, pas encore Azure pronunciation.

## Respect architecture
Documentation uniquement, aucun changement metier.

## Criteres d'acceptation
- Le README decrit fidelement le fonctionnement actuel.
- Le README distingue clairement MVP actuel et roadmap LiveKit/Azure.
- Un developpeur peut lancer le projet sans deviner les commandes principales.

## Verification
- Relecture README.
- Aucun test code requis sauf si des exemples de commandes sont modifies.

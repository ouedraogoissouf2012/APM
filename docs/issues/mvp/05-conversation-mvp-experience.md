## Objectif
Ameliorer l'experience de conversation tour-par-tour pour qu'elle ressemble a un vrai coach MVP.

## Contexte
Le flux actuel fonctionne : mobile STT -> backend turn -> mobile TTS. Il faut maintenant rendre l'experience plus fluide et pedagogique.

## Perimetre
- Ajouter ou definir un message initial d'assistant au demarrage d'une session.
- Ameliorer le prompt selon CEFR, scenario, interets et objectif.
- Gerer proprement speech vide, micro indisponible, backend indisponible.
- Garder un transcript coherent pour le bilan.

## Respect architecture
- La logique conversation backend reste dans `features/conversation`.
- La logique UI reste dans les view models/widgets.
- Les repositories restent responsables des appels API.

## Criteres d'acceptation
- Une session commence avec un contexte clair.
- Les scenarios influencent visiblement les reponses.
- Les erreurs courantes affichent un message utile.
- Le transcript reste exploitable par le debrief.

## Verification
- Tests unitaires prompt/service.
- Tests view model conversation.
- `flutter test`
- `uv run pytest tests/unit -q`

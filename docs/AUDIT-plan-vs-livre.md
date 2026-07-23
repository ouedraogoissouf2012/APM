# Audit honnête — plan de départ vs. ce qui est réellement livré

**Date :** 2026-07-22
**Contexte :** retour utilisateur — « temps de réponse très long ou inexistant »,
« l'IA lit juste le texte », « ne répond à aucun attendu du plan de départ ».
**But :** confronter, sans complaisance, la spec MVP validée le 2026-06-02 à
l'état réel du code, pour décider en connaissance de cause.

> Chaque ligne « Livré » est vérifiée dans le code actuel, pas de mémoire.

---

## 1. Périmètre MVP (spec §3) — promesse vs. réalité

| # | Promesse du plan (v1) | Réellement livré | Écart | Cause |
|---|---|---|---|---|
| 1 | Inscription / connexion | ✅ JWT + refresh, rate-limit | Aucun | — |
| 2 | Scénarios guidés (5-6) + mode libre | ✅ 5 scénarios + libre | Aucun (manque « présentation ») | Mineur |
| 3 | **Conversation vocale temps réel continue (type appel)** | ⚠️ **Tour-par-tour**, pas temps réel | **Majeur** | Pivot MVP : LiveKit retiré |
| 4 | Mémoire persistante (profil, intérêts, résumé, erreurs) | ⚠️ Profil + résumé simple ; pas de mémoire vectorielle | Partiel | MVP simplifié |
| 5 | Bilan intelligent (faute→règle→phrase) + ERRANT | ⚠️ Bilan LLM oui ; **ERRANT différé** | Partiel | spaCy lourd (issue #35) |
| 6 | CEFR + difficulté adaptative | ✅ Estimation CEFR + prompt par niveau | Aucun | — |
| 7 | **Score de prononciation par phonème (Azure)** | ❌ **Non implémenté** | **Majeur** | Épic #4 jamais fait (clé Azure) |
| 8 | Historique sessions + erreurs | ✅ Historique présent | Aucun | — |
| 9 | Tiers gratuit ~10 min/j + essai + abonnement | ⚠️ Quota 10 min oui ; **pas de paiement** | Partiel | Stripe = épic #7 post-MVP |

**Score de conformité MVP : 4 complets / 5 partiels-ou-manquants sur 9.**

---

## 2. Stack voix (spec §4) — l'écart le plus lourd

C'est ici que se joue « l'IA lit juste le texte » et « temps de réponse long ».

| Couche | Plan de départ | Livré | Conséquence ressentie |
|---|---|---|---|
| Orchestration voix | **LiveKit Agents** (WebRTC, type appel) | Aucune — HTTP tour-par-tour | Pas de flux continu ; on attend chaque tour |
| STT (reconnaissance) | **Deepgram** (~500-800 ms, cloud) | `speech_to_text` **sur l'appareil** (gratuit) | Qualité variable selon le device/navigateur |
| LLM | GPT-4o-mini / Gemini Flash | **DeepSeek** (`deepseek-chat`) | OK, mais **réponse en bloc, pas de streaming** |
| TTS (voix) | **Cartesia / ElevenLabs** (voix neuronale) | `flutter_tts` **du système** | **Voix robotique — « il lit juste le texte »** |
| Premium S2S | `gpt-realtime` / Gemini Live | Aucun | Pas de voix S2S naturelle |
| Prononciation | **Azure Pronunciation Assessment** | Aucun | Le différenciateur n°1 du produit absent |

### Pourquoi c'est comme ça (le « pivot » non négocié avec toi)

La mémoire projet documente un « pivot créatif » : tu n'avais qu'une **clé
DeepSeek**, pas de budget LiveKit/Deepgram/TTS payant. La décision a donc été
prise de tout faire **sur l'appareil et gratuitement**. C'était raisonnable
pour valider le cœur pédagogique sans frais — **mais le résultat sensoriel
(voix robotique, latence, pas de temps réel) est très loin de la vision**, et
cet écart n'a jamais été mis franchement sous tes yeux. C'est le vrai sujet.

---

## 3. Anatomie de la latence (mesurée le 2026-07-22)

Un appel DeepSeek réel mesuré : **2,0 s** pour une réponse courte. Mais le tour
complet est **100 % séquentiel, rien ne se chevauche** :

```
Tu finis de parler
  └─ ~2,0 s   attente que la reconnaissance conclue (pauseFor = 2 s)
  └─ ~0,1 s   requête HTTP mobile → backend
  └─ 2 à 6 s  le backend attend TOUTE la réponse LLM (pas de stream)
  └─ ~0,1 s   réponse renvoyée au mobile
  └─ puis     le TTS commence SEULEMENT ICI à lire
= 4 à 8 s de silence avant le premier mot prononcé
```

**Deux leviers identifiés :**
- **Streaming** (le gros gain) : `deepseek.py` appelle l'API **sans**
  `stream=True` → on attend la réponse entière. En streamant, le TTS peut
  démarrer dès la première phrase → temps perçu ~2 s au lieu de 4-8 s.
- **Réglages** : `pauseFor = 2 s` et `max_tokens = 400` allongent chaque tour.

---

## 4. Ce qui est SAIN (à ne pas jeter)

L'audit serait malhonnête s'il ne disait que le négatif. Le socle est bon :
- Architecture propre (SOLID, feature-first, ~170 tests verts, `analyze` 0).
- Le cœur pédagogique fonctionne : parler → réponse IA → bilan CEFR.
- Le design system livré est fidèle à la vision (VoiceOrb, bilan cream…).
- Les fondations (auth, quotas, transcripts, mémoire simple) sont solides.

Le problème n'est **pas** la qualité du code. C'est que **l'ambition
sensorielle du plan a été volontairement rabaissée au niveau MVP-gratuit**,
et que cet arbitrage n'a pas été assez explicite.

---

## 5. Chemin pour combler l'écart — par coût

### Gratuit (aucune clé, je le fais maintenant)
- **Streaming LLM + TTS** → divise le temps perçu par ~2-3. *(en cours)*
- **Meilleure voix système** + réglage débit/intonation → moins robotique. *(en cours)*
- Réglage `pauseFor` / `max_tokens` → tours plus vifs.

### Petit budget (clé API à l'usage)
- **Voix neuronale** (ElevenLabs/Cartesia, ~0,02-0,06 $/min) → voix vraiment
  naturelle. C'est LE saut qualitatif sur « il lit juste le texte ».
- **Prononciation Azure** (5 h gratuites/mois puis ~1 $/h) → le différenciateur
  n°1 du produit, aujourd'hui absent.

### Chantier lourd
- **LiveKit temps réel** (voix continue type appel) → nécessite serveur agent +
  clés STT/TTS/LiveKit. C'est la vision complète, mais un vrai projet.

---

## 6. Recommandation

1. **Maintenant, gratuit** : streaming + voix système améliorée (déjà lancé).
   Ça règle une grande partie de « temps long » et atténue « lit le texte ».
2. **Décision à prendre** : débloquer un petit budget pour une **voix neuronale**
   — c'est le meilleur rapport impact/coût pour que l'app cesse de « lire ».
3. **Ensuite** : prononciation Azure (différenciateur), puis LiveKit si l'app
   décolle.

Le plan de départ reste atteignable. Mais il faut **assumer que le MVP gratuit
n'est pas le produit du plan** — c'en est le brouillon fonctionnel.

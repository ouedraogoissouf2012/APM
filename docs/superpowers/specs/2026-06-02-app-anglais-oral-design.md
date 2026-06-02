# Spécification — APM (Anglais Pour Moi) : application mobile d'apprentissage de l'anglais oral par IA

**Date :** 2026-06-02
**Statut :** Design validé
**Nom :** **APM — Anglais Pour Moi**
**Public de lancement :** francophones d'abord, puis extension multilingue (v2)

---

## 1. Vision

Une application mobile où l'utilisateur a une **vraie conversation parlée** en anglais avec une IA, sans pression, et qui lui remet à la fin un **bilan clair de ses erreurs** (faute → règle de grammaire → bonne formulation) dans sa langue maternelle, accompagné d'un **score de prononciation par phonème**.

### Le différenciateur central (« moat »)

Aucun produit du marché ne combine aujourd'hui :
1. une **notation de prononciation au niveau du phonème** (force d'ELSA, mais ELSA ne sait pas converser) ;
2. une **conversation libre et profonde** (force de Langua/Loora/Praktika, mais leur prononciation est faible) ;
3. une **mémoire persistante** du profil et des conversations passées (manque quasi universel : les concurrents « oublient » d'une session à l'autre et reposent toujours les mêmes questions).

La fusion de ces trois éléments est l'espace laissé vide par les leaders.

### Pièges du marché à éviter

- **Reconnaissance vocale trop indulgente** : la plainte n°1 des utilisateurs. Des apps affichent « Perfect ! » même sur une mauvaise prononciation (TalkPal ~25 % de précision mesurée ; Speak valide des phrases dans le désordre). → **On sera honnête** : seuils calibrés, score réel affiché. C'est ce qui crée la confiance et la vraie progression.
- **Feedback qui casse le flux** (modales à cliquer en pleine conversation). → bilan **en différé**.
- **Billing/remboursements opaques**. → essai transparent, remboursement simple.

---

## 2. Principes pédagogiques (fondés sur la recherche)

Chaque fonction du produit est ancrée dans la recherche en acquisition des langues (SLA) :

| Principe (source) | Application produit |
|---|---|
| **Output > Input** (Swain, Output Hypothesis) | L'apprenant parle ≥ 60 % du temps ; questions ouvertes, tâches « décris/explique/convaincs ». |
| **Elicitation > recast** (Lyster & Saito 2010) | Sur une erreur, on pousse l'apprenant à **se corriger lui-même** (indice/règle) plutôt que reformuler en douce — les recasts sont ignorés ~70 % du temps. |
| **Correction en différé** | Pendant la conversation libre, on n'interrompt pas ; bilan focalisé sur 2-3 erreurs utiles à la fin. |
| **Filtre affectif bas** (Krashen ; FLA, Horwitz) | Partenaire IA patient, zéro jugement = avantage majeur de l'IA sur un prof humain. |
| **Niveau CEFR auto** | Estimation du niveau (A1→C2) à partir de la parole ; difficulté ajustée en continu (i+1). |
| **Scaffolding / release graduelle** (Vygotsky, ZPD) | Amorces de phrases au début, retirées à mesure que l'apprenant réussit. |
| **HVPT + paires minimales** (méta-analyse g≈0,71-0,92) | *(v2)* Entraînement perceptif multi-voix → se généralise à de nouveaux mots. |
| **SRS des erreurs** (effet d'espacement + effet de test) | *(v1.1)* Les fautes passées reviennent dans de futures conversations à intervalles espacés. |
| **Technique 4/3/2** (Nation) | *(v1.1)* Drill de fluidité : même sujet en 4, puis 3, puis 2 min. |

**Mythes écartés (à ne pas reproduire) :** « l'input seul suffit » (faux : il faut de la production) ; « les intervalles croissants du SRS sont prouvés supérieurs » (non, contesté) ; statistiques marketing « +200-400 % de rétention » (sans base scientifique). Le shadowing aide la prosodie/fluidité, pas les phonèmes isolés.

---

## 3. Périmètre

### MVP (v1)

1. Inscription / connexion (compte utilisateur).
2. **Scénarios guidés** (5-6 : restaurant, voyage, présentation, entretien d'embauche, small talk, achats) + **mode libre** basique.
3. **Conversation vocale temps réel** continue (type appel), sans interruption.
4. **Mémoire persistante** : profil, intérêts, résumé des conversations passées, erreurs récurrentes.
5. **Bilan d'erreurs intelligent** de fin de session : faute → règle → bonne phrase, dans la langue maternelle, avec elicitation et catégorisation ERRANT.
6. **Niveau CEFR + difficulté adaptative** (version simple : estimation à partir du transcript + métriques, ajustement du prompt).
7. **Score de prononciation par phonème** (Azure) : carte colorée vert/jaune/rouge par mot/phonème, replay de sa voix.
8. **Historique** des sessions et des erreurs (révision).
9. **Tiers de paiement** : gratuit (~10 min/jour) + essai 7 jours ; abonnement.

### Reporté

- **v1.1** : SRS des erreurs · drill de fluidité 4/3/2 · choix d'accent (US/UK).
- **v2** : scénarios générés à la volée · entraînement HVPT paires minimales · widget streak · débats · multilingue étendu de l'UI.

### Hors périmètre (YAGNI pour l'instant)

Gamification poussée/classements, partage social, mode hors-ligne, avatars 3D.

---

## 4. Stack technique

| Couche | Choix | Justification |
|---|---|---|
| **Mobile** | **Flutter** (Dart) | Perf UI/animations supérieures (utile pour les visualisations de prononciation) ; SDK LiveKit Flutter officiel (`livekit_client` + `flutter_webrtc`) ; client agnostique du fournisseur IA (parle WebRTC au LiveKit Agent). |
| **Backend** | **Python / FastAPI** | Async-natif (appels IA concurrents, streaming, WebSockets) ; **même langage que tout l'écosystème IA/voix** : LiveKit Agents (Python), ERRANT (Python), CrisperWhisper (Python). |
| **Base de données** | **PostgreSQL** | Relationnel, robuste, JSON natif pour les bilans/scores. |
| **Voix temps réel** | **LiveKit Agents** (orchestration WebRTC) | SDK Flutter + serveur Python ; permet de basculer entre moteurs sans changer le client. |
| **Moteur voix — défaut/gratuit** | Pipeline **Deepgram (STT) + GPT-4o-mini/Gemini Flash (LLM) + Cartesia/ElevenLabs Flash (TTS)** | ~0,02-0,06 $/min, latence ~500-800 ms, **transcript parfait offert**. |
| **Moteur voix — premium** | **OpenAI `gpt-realtime`** (S2S, WebRTC) ou **Gemini Live** | Voix la plus naturelle, gestion native des interruptions. Réservé au tier payant. |
| **Prononciation** | **Azure AI Speech — Pronunciation Assessment** | Scores phonème/mot/prosodie, IPA, ~1 $/h, conçu pour les non-natifs, 5 h gratuites/mois. |
| **Bilan grammaire** | **LLM (sortie JSON stricte) + ERRANT** (validation/typage), async | Anti-hallucination : ancrage sur le texte réel + rejet des « corrections » qui ne mappent à rien. |
| **Fluidité** | **CrisperWhisper** (transcript verbatim, pauses, fillers) | Whisper standard supprime les « euh » → fausse les métriques ; CrisperWhisper les garde. |

### Stratégie de coût (intuition « IA seulement là où il faut »)

- La voix temps réel ne tourne **que** pendant la conversation.
- Le bilan, la grammaire, le CEFR, le contenu des scénarios, les règles → LLM bon marché en **asynchrone**, cache, ou base de données.
- **Prompts système courts** en temps réel (les longs prompts re-envoyés à chaque tour sont le coût caché n°1).
- L'IA reste **concise** : l'apprenant parle le plus → meilleur pédagogiquement ET moins cher (le coût est dominé par l'audio de sortie).
- **Quotas par utilisateur** imposés côté backend.
- **Défaut = pipeline pas cher** ; le S2S premium est derrière le tier payant.

### Sécurité

- L'appli mobile ne contient **jamais** de clé API.
- Le backend authentifie l'utilisateur puis émet un **jeton éphémère** (LiveKit room token ; clé éphémère OpenAI ~60 s).
- Le média audio passe en **WebRTC direct** appli ↔ LiveKit (pas de proxy serveur → latence/coût minimaux), mais seulement après le jeton.
- Le backend impose auth + quotas et stocke les transcripts.

---

## 5. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                APPLI MOBILE (Flutter)                     │
│  • UI conversation · carte prononciation · bilan · profil │
│  • Client WebRTC (LiveKit Flutter SDK)                    │
└───────────────┬──────────────────────────┬───────────────┘
                │ 1. Auth + jeton éphémère  │ 3. Média audio (WebRTC, direct)
                ▼                            ▼
┌───────────────────────────┐   ┌──────────────────────────┐
│   BACKEND (FastAPI)        │   │   LiveKit Agent (Python)  │
│  • Auth, comptes, quotas   │   │  • Pipeline STT→LLM→TTS   │
│  • Émet jetons éphémères   │◄──┤  • ou S2S premium         │
│  • Stocke transcripts      │ 2 │  • Injecte mémoire+prompt │
│  • Bilan async (LLM+ERRANT)│   │  • Capture le transcript  │
│  • Profil mémoire, CEFR    │   └──────────────────────────┘
└──────┬─────────────┬───────┘            │
       ▼             ▼                     ▼
┌────────────┐ ┌─────────────┐   ┌──────────────────┐
│ PostgreSQL │ │ Azure Pron. │   │  Services IA      │
│ (données)  │ │ Assessment  │   │ OpenAI/Gemini/    │
└────────────┘ └─────────────┘   │ Deepgram/Cartesia │
                                 └──────────────────┘
```

---

## 6. Composants (rôle unique chacun)

### Appli mobile (Flutter)

- **`Conversation`** — pilote l'appel vocal WebRTC, affiche les sous-titres en direct.
- **`PronunciationView`** — carte colorée vert/jaune/rouge par mot/phonème, replay.
- **`DebriefView`** — bilan de fin : faute → règle → bonne phrase (langue maternelle).
- **`Profile / Progress`** — niveau CEFR, historique, courbe de progression.
- **`ScenarioPicker`** — scénarios guidés + entrée mode libre.

### Backend (FastAPI)

- **`auth`** — comptes, sessions, émission des jetons éphémères.
- **`conversation-service`** — démarre/termine les sessions, applique les quotas.
- **`voice-agent`** (LiveKit Agent) — orchestre STT→LLM→TTS, injecte mémoire + prompt adapté au niveau, capture le transcript.
- **`debrief-service`** — analyse async : LLM (JSON structuré) + validation ERRANT + estimation CEFR.
- **`pronunciation-service`** — envoie l'audio à Azure, normalise les scores phonèmes.
- **`memory-service`** — profil apprenant, intérêts, résumé des conversations passées, erreurs récurrentes.
- **`billing`** — tiers gratuit/payant, quotas de minutes.

---

## 7. Modèle de données (PostgreSQL — esquisse)

- **`users`** : id, email, langue_maternelle, niveau_cefr_courant, tier, minutes_consommées, créé_le.
- **`learner_profile`** : user_id, intérêts (JSON), objectif (« ideal L2 self »), préférences (intensité correction, accent).
- **`sessions`** : id, user_id, type (scénario/libre), scénario_id, début, fin, durée, moteur_voix.
- **`transcripts`** : id, session_id, tours (JSON : rôle, texte, timestamps).
- **`errors`** : id, session_id, span_original, span_corrigé, type_errant, tag_cefr, règle, confiance, uptake (corrigé ou non). *(alimente le SRS en v1.1)*
- **`pronunciation_scores`** : id, session_id, mot, phonèmes (JSON), score_précision, score_prosodie.
- **`fluency_metrics`** : id, session_id, débit, pauses, fillers, longueur_moyenne_run.
- **`conversation_memory`** : user_id, résumés (JSON) des sessions passées, faits sur l'utilisateur.

---

## 8. Déroulé d'une session (data flow)

1. L'utilisateur choisit un scénario → l'appli demande un **jeton éphémère** au backend (qui vérifie le quota).
2. L'appli ouvre l'audio **WebRTC direct** vers le LiveKit Agent.
3. L'agent charge la **mémoire** (profil, erreurs récurrentes, niveau) et règle la difficulté à **i+1**.
4. Conversation naturelle, **sans interruption** ; le transcript est capturé côté serveur.
5. À la fin → traitements **async en parallèle** :
   - **Bilan grammaire** (LLM + ERRANT) → liste « faute → règle → correction ».
   - **Score prononciation** (Azure) → carte phonèmes.
   - **Niveau CEFR** + métriques de fluidité (CrisperWhisper).
   - Mise à jour de la **mémoire** (résumé, nouvelles erreurs).
6. L'appli affiche le bilan ; les données alimentent la progression (et, en v1.1, le SRS).

---

## 9. Gestion des erreurs & qualité

- **Honnêteté ASR** : jamais de « Perfect » à tort ; seuils calibrés ; score réel affiché.
- **Anti-hallucination du bilan** : sortie JSON stricte (`json_schema`, `strict: true`) + ancrage par offsets sur le texte réel + validation ERRANT (rejet de toute correction no-op) + prompt « édition minimale » contre la surcorrection.
- **Biais CEFR** : les LLM surestiment B2 → ancrage few-shot + métriques objectives en complément.
- **Coupure réseau** : conversation sauvegardée par tours ; reprise possible.
- **Dépassement de quota** : message clair + proposition d'upgrade (pas de coupure brutale).
- **Latence** : pipeline visé < 800 ms ; repli automatique si un service tombe.

---

## 10. Tests

- Tests unitaires backend (quotas, jetons, parsing du bilan).
- Tests d'intégration des services IA avec réponses simulées (mocks).
- Validation du schéma JSON du bilan sur un jeu de transcripts réels.
- Tests E2E mobile sur les parcours clés (connexion → conversation → bilan).
- **TDD** : tests écrits avant l'implémentation.

---

## 11. Modèle économique

- **Gratuit** : ~10 min/jour de conversation + essai 7 jours complet.
- **Abonnement de masse** : ~99 €/an (~8-10 €/mois).
- **Premium** : ~149-199 €/an — prononciation phonème illimitée + minutes premium (voix S2S).

⚠️ **Production** : un abonnement personnel (ChatGPT Plus, etc.) ne permet pas de faire tourner une appli publique — il faut des **clés API** facturées à l'usage. L'abonnement personnel peut servir au développement/tests perso au début.

---

## 12. Risques & points à vérifier au moment du build

- Stabilité du modèle Gemini Live (preview) — vérifier avant de s'y engager.
- Tarifs STT/TTS et `gpt-realtime-mini` évoluent vite — confirmer sur les pages live.
- Prosody scoring d'Azure : **en-US uniquement**.
- L'évaluation de contenu intégrée d'Azure (grammaire/vocab) est **retirée** (SDK ≥1.46) → on possède cette couche via LLM (déjà prévu).
- Conformité : RGPD (données vocales = données personnelles), consentement enregistrement, stockage UE.
- Modération : filtrer les contenus inappropriés en conversation libre.

---

## Roadmap

- **MVP (v1)** : conversation + mémoire + bilan intelligent + CEFR adaptatif + prononciation phonème.
- **v1.1** : SRS des erreurs · drill 4/3/2 · choix d'accent US/UK.
- **v2** : scénarios générés à la volée · HVPT paires minimales · widget streak · débats.

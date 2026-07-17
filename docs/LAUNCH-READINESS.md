# APM — Préparation au lancement

> État consolidé au 2026-06-05. Objectif : donner une feuille de route honnête entre « MVP vérifié » et « app publiée ».

---

## 1. Ce qui est construit et **vérifié à l'exécution**

Parcours complet, fonctionnel avec **la seule clé DeepSeek** :

```
Auth → Onboarding → Profil (intérêts/objectif/accent)
   → Scénario (restaurant, entretien, voyage, small talk, shopping) ou mode libre
   → Conversation orale tour-par-tour (micro STT natif → DeepSeek → voix TTS native)
       · adaptée au niveau CEFR · recasts sans couper · questions ouvertes · mémoire des sessions passées
   → Fin → Bilan (faute → règle → correction, en langue maternelle) + estimation CEFR
       · anti-hallucination (chaque faute ancrée sur le texte réel)
       · niveau CEFR qui évolue d'une session à l'autre (i+1)
   → Carte de prononciation (UI prête, affichage honnête — en attente d'une source de scores)
   → Historique des sessions + courbe de progression CEFR
```

**Preuves** (session de vérif du 2026-06-05) :
- Conversation réelle DeepSeek : recasts corrects, niveau A1, questions ouvertes ✅
- Bilan réel : 5 corrections exactes + CEFR A2 + résumé français, anti-hallucination OK ✅
- Backend : **157 tests** (ruff + mypy verts) · Mobile : ~57 tests + `flutter analyze` clean

## 2. Architecture (résumé)

- **Backend** : FastAPI + SQLAlchemy 2.0 async + PostgreSQL, **feature-first** (`app/features/{auth,profile,sessions,conversation,debrief}`), couches API→Service→Repository→Domain, erreurs centralisées, logging JSON, rate-limiting, refresh tokens.
- **Mobile** : Flutter, **MVVM + Riverpod** (sans codegen), go_router, dio, `speech_to_text` + `flutter_tts` (voix **on-device**, gratuit).
- **Voix** : pivot créatif **on-device STT/TTS + DeepSeek** (texte). Pas de LiveKit/Deepgram/TTS payant. Endpoint `POST /sessions/{id}/turn`.

## 3. Lancer en local (récapitulatif + pièges connus)

**Prérequis** : Docker Desktop démarré, `uv`, Flutter 3.38, une **clé API DeepSeek** (platform.deepseek.com, ~1-2 $ de crédit).

```powershell
# 1) Base de données
docker compose up -d postgres

# 2) Backend
cd backend
#   .env : mettre DEEPSEEK_API_KEY=sk-...  et  VOICE_ENGINE=deepseek  DEBRIEF_ENGINE=deepseek
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload      # http://localhost:8000/docs

# 3) Mobile (Chrome)
cd ../mobile
flutter run -d chrome
```

⚠️ **Pièges appris** (à ne pas réoublier) :
- **Chemin ASCII obligatoire pour le build web.** Un chemin avec accent/espace (`…\propre à moi\…`) casse le compilateur de shaders Flutter. Le repo vit désormais dans **`C:\dev\apm`** pour cette raison.
- Les tests **n'appellent jamais** le vrai DeepSeek (forcé `fake` dans `conftest`) → pas de coût, pas de flakiness. `.env` peut rester sur `deepseek` pour les vrais runs.
- Sans clé DeepSeek, `POST /turn` renvoie un **502** propre (pas un crash).

## 4. Ce qui manque pour **publier** (checklist)

**Bloqué sur des clés/services externes (optionnel selon l'ambition) :**
- [ ] **Prononciation par phonème** (#4) — clé **Azure AI Speech**. L'UI est prête ; il faut la source de scores. *(Ne pas remplacer par un proxy de confiance STT : trompeur, érode la confiance.)*
- [ ] **Conversation temps réel full-duplex** (#69) — compte **LiveKit Cloud** + STT/TTS temps réel. **Optionnel** : le tour-par-tour on-device est déjà un MVP viable.

**Décisions produit / business :**
- [ ] **Billing** (#7) — Stripe, tiers gratuit/premium, essai 7 j. Les quotas de minutes existent déjà côté backend.
- [ ] **Modération** du contenu en conversation libre (filtrage).
- [ ] **RGPD** : données vocales = données perso — consentement, stockage UE, politique de conf.

**Mise en production (technique) :**
- [ ] **Héberger le backend** (conteneur FastAPI) + **PostgreSQL managé** (Neon/Supabase/RDS…). Variables d'env prod (secrets管理, pas de `.env` en clair).
- [ ] **Secrets** : `JWT_SECRET` fort (≥32 octets), clé DeepSeek en secret manager.
- [ ] **CORS** : restreindre `CORS_ALLOW_ORIGINS` au domaine de l'app (pas `*` en prod).
- [ ] **Build stores** : Android (signing, `flutter build appbundle`) + iOS (certs, `flutter build ipa`) ; icônes, splash, permissions micro déjà en place.
- [ ] **CI** : recharger les crédits GitHub Actions (épuisés) pour relancer lint+types+tests sur PR.
- [ ] **Observabilité** : brancher les logs JSON à un agrégateur ; métriques d'usage.

## 5. Limites honnêtes (à assumer / communiquer)

- Conversation **tour-par-tour** (écoute → réfléchit → parle), pas un appel continu. Acceptable pédagogiquement, mais moins « fluide » qu'une vraie voix temps réel.
- **Voix de l'appareil** (correcte, pas premium type ElevenLabs).
- **Prononciation phonème absente** tant qu'Azure n'est pas branché (l'app ne prétend jamais le contraire — affichage honnête « pas assez de données »).
- Qualité pédagogique = celle de **DeepSeek** (bonne, mais à surveiller sur les cas limites : sur/sous-correction, estimation CEFR).

## 6. Sécurité — actions immédiates

- [ ] **Régénérer la clé DeepSeek** exposée pendant le dev, la remettre dans `C:\dev\apm\backend\.env` (jamais dans `.env.example`).
- [ ] Vérifier qu'aucun secret n'est dans un fichier suivi (fait : `.env` ignoré, `.env.example` sans clé).

## 7. Coûts (ordre de grandeur)

- **DeepSeek** : ~centimes / conversation (deepseek-chat, prompts courts, max tokens bornés). Le poste principal.
- **STT/TTS** : **0** (on-device).
- **Hébergement** : petit VPS + Postgres managé (~10-20 €/mois pour démarrer).
- **Azure prononciation** (si activé) : ~1 $/h d'audio, 5 h/mois gratuites.

---

**Verdict :** le **produit-cœur est prêt et vérifié**. Le chemin vers le lancement est surtout de l'**infra + décisions produit**, plus deux fonctionnalités optionnelles bloquées sur des clés (prononciation Azure, temps réel LiveKit). Aucune dette fonctionnelle cachée.

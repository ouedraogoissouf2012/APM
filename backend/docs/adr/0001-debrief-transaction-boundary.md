# ADR 0001 — Frontière transactionnelle du débrief : cœur atomique + enrichissements best-effort post-commit

- **Statut** : accepté (2026-08-06, audit-4 / #188)
- **Portée** : `POST /sessions/{id}/debrief` et, par extension, tout endpoint qui
  écrit un enregistrement autoritaire PUIS déclenche des effets secondaires.

## Contexte

`DebriefService.generate()` était un god-orchestrator : ~6 commits sur la session
de requête partagée, mêlant l'écriture **autoritaire** (le débrief, le nudge CEFR,
le résumé mémoire) et des **enrichissements** (vocabulaire, SRS, analytics). Deux
défauts systémiques en découlaient :

1. **Pas de frontière transactionnelle par requête.** Chaque sous-opération
   committait indépendamment. Un échec en milieu de chaîne laissait un état
   partiel (ex. débrief sauvé mais mémoire non écrite).
2. **Le guard « débrief déjà existant → return » figeait les échecs partiels.**
   Comme `generate()` renvoie tôt si un débrief existe, un enrichissement échoué
   (avalé en best-effort) n'était **jamais réparé** au rejeu.

## Décision

**Cœur autoritaire ATOMIQUE + enrichissements BEST-EFFORT exécutés après le commit
du cœur.**

- **Cœur autoritaire** = la ligne `Debrief` + le nudge `users.cefr_level` + le
  `learner_profiles.memory_summary`. Ces trois écritures forment l'enregistrement
  que l'apprenant voit et qui pilote les prompts futurs ; elles sont **tout-ou-rien**
  dans **une seule transaction** (un seul `commit`). Comme les trois repositories
  partagent la session de requête, on **stage** le CEFR et la mémoire *avant*
  l'unique commit du repository de débrief : ce commit persiste les trois ensemble.
  Aucun framework Unit-of-Work n'est nécessaire — la session partagée **EST** l'unité
  de travail de la requête ; le contrat « une écriture autoritaire = un commit » est
  tenu par l'ordre de staging, pas par des commits multiples.
- **Enrichissements** = vocabulaire (#116), SRS (#117), analytics (#129). Ils
  s'exécutent **après** que le cœur est durable, orchestrés par un petit dispatcher
  (`PostDebriefEnrichment`), chacun **best-effort** (échec journalisé, jamais fatal)
  et **idempotent quand c'est bon marché**. Un hoquet analytics ne doit jamais priver
  l'apprenant de son débrief.

## Alternatives rejetées

- **Tout-atomique (une transaction pour cœur + enrichissements)** : un échec vocab
  ou analytics ferait échouer TOUT le débrief. Mauvais compromis — un enrichissement
  non-autoritaire ne doit pas nier le livrable autoritaire.
- **Tout-rejouable (effets idempotents réparés au rejeu)** : exige un SRS idempotent
  alors qu'il est **dépendant du temps** (rejouer `record_session` à un `now`
  ultérieur avance le planning différemment). Disproportionné pour le gain.

## Conséquences

- **Positif** : un échec du **cœur** ne persiste rien → le rejeu re-exécute
  proprement (pas de double-promotion CEFR). Un échec d'**enrichissement** renvoie
  quand même le débrief. `generate()` est réduit à de l'orchestration ; chaque effet
  vit dans son service.
- **Dette tracée (assumée, non masquée)** :
  1. **Réparation des enrichissements au rejeu** : le guard « débrief existant →
     return » ne relance PAS les enrichissements échoués. Mitigation immédiate :
     l'**activation** analytics est rendue idempotente (émise seulement après une
     complétion réussie, et une seule par utilisateur). Réparation complète (rejouer
     tous les enrichissements manquants) = un futur outbox/worker.
  2. **Le sink analytics commite la session partagée.** Comme il tourne **en dernier**
     (après le commit du cœur), son commit ne flushe que ses propres lignes. Le
     découplage complet (session dédiée / outbox) reste à faire.

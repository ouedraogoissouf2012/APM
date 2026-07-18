# EAnglais — Spécification Design & Prompt d'implémentation

> Fichier destiné à Claude Code. Place-le à la racine du projet Flutter (`mobile/DESIGN_SPEC.md`)
> et référence-le depuis ton `CLAUDE.md` : « Toujours respecter DESIGN_SPEC.md pour toute UI. »

---

## PROMPT PRINCIPAL (à coller dans Claude Code pour démarrer)

```
Lis DESIGN_SPEC.md en entier avant d'écrire du code.

Implémente le design system d'EAnglais dans lib/theme/ puis les composants
signature dans lib/widgets/ en respectant STRICTEMENT les tokens, la
typographie et les animations décrits. Commence par :

1. lib/theme/app_colors.dart — tous les tokens couleurs
2. lib/theme/app_typography.dart — Fraunces + Inter via google_fonts
3. lib/theme/app_theme.dart — ThemeData dark (défaut) et light (bilan)
4. lib/widgets/voice_orb.dart — l'orbe vocal animé (composant signature)
5. lib/widgets/correction_chip.dart — le chip de correction doré

Ne dévie jamais des valeurs hexadécimales et des règles de ce fichier.
À la fin, montre-moi chaque composant dans une page de démo lib/dev/gallery_page.dart.
```

---

## 1. Identité

- **Nom** : eanglais — wordmark en Fraunces Light, le mot "anglais" en italique clay.
- **Tagline** : « Parle. Trompe-toi. Progresse. »
- **Positionnement** : le partenaire de conversation anglaise le plus honnête et le
  plus mémoriel. Éditorial, premium, chaleureux. JAMAIS enfantin/gamifié façon Duolingo.
- **Principe clé** : l'erreur n'est jamais rouge. Elle est **dorée** — précieuse,
  c'est de la matière à apprendre.

## 2. Tokens couleurs (`app_colors.dart`)

```dart
class AppColors {
  // Fonds sombres (mode conversation, défaut)
  static const ink        = Color(0xFF0D0F15); // fond principal
  static const inkDeep    = Color(0xFF08090D); // fond device / bas de page
  static const surface    = Color(0xFF13161D); // cartes
  static const surfaceAlt = Color(0xFF161A22); // orbe anneau externe
  static const surfaceHi  = Color(0xFF1F2530); // orbe anneau interne
  static const border     = Color(0xFF1E212A); // bordures cartes
  static const borderHi   = Color(0xFF23262E); // bordures fortes

  // Fonds clairs (mode bilan / carnet — inversion lumineuse)
  static const cream      = Color(0xFFF5F1E8); // fond bilan
  static const creamCard  = Color(0xFFFFFDF8); // cartes sur cream
  static const creamBorder= Color(0xFFE5DECB);
  static const inkWarm    = Color(0xFF1A1206); // texte sur cream + carte "mot du jour"

  // Accents
  static const clay       = Color(0xFFE8623D); // couleur de marque, actions, voix
  static const clayLight  = Color(0xFFEE7E5C); // cercles décoratifs
  static const clayPale   = Color(0xFFF5A183);
  static const clayDark   = Color(0xFF4A1B0C); // texte sur fond clay
  static const clayOnCream= Color(0xFFB5502E); // clay lisible sur cream
  static const gold       = Color(0xFFD4B36A); // corrections + vocabulaire UNIQUEMENT
  static const goldBg     = Color(0xFF2A2113); // fond chip correction
  static const goldBorder = Color(0xFF4A3A1A);
  static const green      = Color(0xFF8FB57A); // statut positif, "en direct"
  static const greenCream = Color(0xFF5E8A4A); // vert sur fond cream

  // Textes
  static const textPrimary   = Color(0xFFF5F1E8); // sur sombre
  static const textSecondary = Color(0xFFB9BDC7);
  static const textMuted     = Color(0xFF7A7E88);
  static const textFaint     = Color(0xFF4A4E58); // icônes inactives
  static const textMutedWarm = Color(0xFF8A8272); // muted sur cream
  static const textFaintWarm = Color(0xFFA39A85); // texte barré sur cream
}
```

**Règles d'usage strictes :**
- `gold` est RÉSERVÉ aux corrections et au vocabulaire. Jamais pour la décoration.
- `clay` : une seule action primaire par écran maximum.
- Jamais de rouge pour les erreurs.
- Le mode sombre est le défaut (on parle le soir). Le mode clair (`cream`) est réservé
  au bilan de session et aux flashcards — c'est une **inversion narrative** : on sort
  du tunnel de conversation, on prend la lumière pour lire son bilan.

## 3. Typographie (`app_typography.dart`)

Dépendance : `google_fonts: ^6.x`

| Rôle | Police | Usage |
|---|---|---|
| **Display / contenu émotionnel** | Fraunces (Light 300, Regular 400) | Greetings, score, mots anglais, transcription de la voix de l'utilisateur, titres de sujets |
| **Display italique** | Fraunces Italic | Accents de marque ("Seven.", "de toi."), traductions, citations |
| **UI fonctionnelle** | Inter (400, 500) | Labels, boutons, navigation, corps de texte, stats labels |

```dart
class AppType {
  static TextStyle displayXl(Color c) => GoogleFonts.fraunces(
      fontSize: 52, fontWeight: FontWeight.w300, height: 1.0, color: c); // score bilan
  static TextStyle displayLg(Color c) => GoogleFonts.fraunces(
      fontSize: 28, fontWeight: FontWeight.w300, height: 1.15, color: c); // greeting
  static TextStyle displayMd(Color c) => GoogleFonts.fraunces(
      fontSize: 20, fontWeight: FontWeight.w400, height: 1.2, color: c);
  static TextStyle transcript(Color c) => GoogleFonts.fraunces(
      fontSize: 19, fontWeight: FontWeight.w300, fontStyle: FontStyle.italic,
      height: 1.45, color: c); // ce que dit l'utilisateur
  static TextStyle body(Color c) => GoogleFonts.inter(fontSize: 14, height: 1.55, color: c);
  static TextStyle label(Color c) => GoogleFonts.inter(
      fontSize: 12, fontWeight: FontWeight.w500, letterSpacing: 0.5, color: c);
  static TextStyle overline(Color c) => GoogleFonts.inter(
      fontSize: 11, letterSpacing: 1.2, color: c); // "JE T'ÉCOUTE", "MÉMOIRE"
}
```

Règle : les **overlines sont en MAJUSCULES** avec letter-spacing. Tout le reste en
casse normale. Jamais de gras 600/700 — uniquement 300/400/500.

## 4. Formes & espacements

- Rayons : cartes 13–15px, cartes hero 17–18px, chips/pills 10–20px, device 24px+.
- Bordures : 1px solid `border`, pas d'ombres portées. Profondeur = superposition de
  surfaces (`ink` → `surface` → `surfaceHi`), pas d'élévation Material.
- `ThemeData` : `useMaterial3: true`, `splashFactory: InkSparkle` désactivé au profit
  de ripples discrets, scaffoldBackgroundColor = `ink`.
- Cercles décoratifs : les cartes clay (ex. "Reprendre") ont 2 cercles pleins
  (`clayLight`, `clayPale`) qui débordent en haut à droite, clippés par le border radius.

## 5. Composants signature

### 5.1 `VoiceOrb` — LE composant de l'app

Structure (du fond vers l'avant) :
1. **Anneaux de propagation** ×2 : cercle bordé 1px `clay`, animation scale 0.92 → 1.18
   + opacity 0.9 → 0, durée 2400ms, `Curves.easeOut`, en boucle, le 2e décalé de 1200ms.
   → `AnimationController` + `ScaleTransition`/`FadeTransition` ou `CustomPainter`.
2. **Disque externe** `surfaceAlt` (170px), **disque médian** `surfaceHi`.
3. **Cœur clay** (~84px) contenant la **waveform** : 5 barres blanches (#FFF7F0),
   largeur 4px, radius 3px, hauteurs [20, 34, 26, 38, 18], animation scaleY 0.35 → 1.0,
   1100ms `Curves.easeInOut` alternée, delays échelonnés de 150ms par barre.
4. **États** : `idle` (anneaux arrêtés, cœur statique avec icône micro),
   `listening` (tout animé), `thinking` (waveform remplacée par 3 points pulsants),
   `speaking` (waveform pilotée par l'amplitude TTS si dispo).

API : `VoiceOrb(state: VoiceOrbState.listening, size: 170)`

### 5.2 `CorrectionChip`
Fond `goldBg`, bordure 1px `goldBorder`, radius 10, padding 5×11.
Icône `sparkles` + texte `gold` 12px : la partie fautive en `lineThrough` opacité 0.6,
flèche →, puis la forme correcte. Apparition : fade + slide-up 250ms, 400ms APRÈS la
fin de la phrase (jamais pendant que l'utilisateur parle — principe de non-interruption).

### 5.3 `TranscriptText`
Fraunces italic light 19px, entre guillemets français « », curseur clignotant
(barre 2×15px `clay`, blink 1s steps) tant que l'écoute est active.

### 5.4 `MemoryCard`
Carte `surface` radius 13. Overline colorée selon la catégorie :
`TON MONDE` (textMuted) / `TON COMBAT` (gold) / `TA VICTOIRE` (green).
Icône edit/supprimer en `textFaint` à droite — TOUT est éditable, c'est la promesse.
"Ton combat" inclut une jauge : 5 segments 4px, progression clay,
sous-texte « 3 sessions sans faute → maîtrisé ».

### 5.5 `SessionScoreCard` (écran bilan, fond cream)
Score en `displayXl` inkWarm (ex. 82) + delta « +6 pts » en `clayOnCream`.
Trois blocs : CE QUI A MARCHÉ (greenCream) / À REPRENDRE (clayOnCream, avec l'erreur
barrée en `textFaintWarm` puis la correction en Fraunces) / MOT DU JOUR (carte inversée
`inkWarm` avec le mot en Fraunces `textPrimary` et la traduction italique `gold`).

### 5.6 `WordCard` (flashcard carnet)
Carte `inkWarm` sur fond cream. Overline gold « VU EN SESSION #23 », mot en Fraunces 26,
phonétique, traduction italique gold entre « », bouton audio rond cream.
Sous la carte : la vraie phrase de l'utilisateur en citation
(« "I handle deployments at work." — toi, mardi dernier »).
Boutons : « Encore » (outline) / « Je le sais » (clay plein).

## 6. Écrans (ordre d'implémentation)

1. **ConversationScreen** — statut pill en haut (dot green + sujet + timer), VoiceOrb
   centré, overline « JE T'ÉCOUTE », TranscriptText, CorrectionChip, barre de contrôle
   (clavier / pause 60px cream / signaler).
2. **SessionSummaryScreen** — fond cream, SessionScoreCard, CTA clay « Ajouter au carnet ».
3. **HomeScreen** — greeting Fraunces (« Good evening, Seven. » — "Seven." en italique
   clay), pill streak, carte clay « REPRENDRE » avec cercles décoratifs, section
   « CE SOIR, ON PARLE DE… » avec suggestions contextuelles (icône colorée + titre +
   niveau·durée), bottom nav 4 items (Parler actif en clay).
4. **MemoryScreen** — titre « Ce que je sais *de toi.* », sous-titre « Tout est
   éditable. Rien n'est caché. », liste de MemoryCard, bouton dashed « + Apprends-moi
   autre chose ».
5. **VocabularyScreen** — WordCard swipeable, compteur, dots de progression.
6. Puis : Onboarding (4 écrans), ProgressScreen, ProfileScreen, Paywall.

## 7. Motion

- Durées : micro-interactions 150–250ms, transitions d'écran 300ms, ambiance
  (orbe, anneaux) 1100–2400ms en boucle.
- Courbes : `easeOut` par défaut, `easeInOut` pour les boucles.
- Transition Conversation → Bilan : fade du fond `ink` → `cream` en 450ms
  (l'inversion lumineuse doit se SENTIR).
- Respecter `MediaQuery.disableAnimations` (accessibilité).

## 8. Voix & ton des textes UI

- Tutoiement, chaleureux, direct. Français pour l'UI, l'anglais est le contenu.
- Jamais culpabilisant : « À reprendre », pas « Erreurs ».
- La mémoire parle à la 1re personne de l'app : « Ce que je sais de toi »,
  « Apprends-moi autre chose ».

## 9. Interdits

- ❌ Rouge pour les erreurs — toujours gold.
- ❌ Ombres portées Material / élévations — superposition de surfaces uniquement.
- ❌ Gras 600+, Title Case sur les labels, emoji dans l'UI.
- ❌ Confettis, mascottes, badges enfantins.
- ❌ Interrompre l'utilisateur pendant qu'il parle (les corrections attendent la fin).

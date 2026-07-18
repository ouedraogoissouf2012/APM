import 'dart:ui';

/// Palette brute — contrat DESIGN_SPEC §2. Valeurs hexadécimales exactes.
///
/// RÈGLE : aucun widget ne référence cette classe directement.
/// Les widgets consomment [AppSemanticColors] via `context.colors`
/// (voir app_theme.dart) ; seul le module `core/theme/` mappe
/// palette brute → rôles sémantiques. Changer de marque = changer ici.
///
/// Règles d'usage strictes (DESIGN_SPEC) :
/// - `gold` est RÉSERVÉ aux corrections et au vocabulaire.
/// - `clay` : une seule action primaire par écran maximum.
/// - Jamais de rouge pour les erreurs.
/// - Sombre = défaut (conversation) ; cream = bilan/carnet uniquement.
abstract final class AppColors {
  // Fonds sombres (mode conversation, défaut)
  static const ink = Color(0xFF0D0F15); // fond principal
  static const inkDeep = Color(0xFF08090D); // fond device / bas de page
  static const surface = Color(0xFF13161D); // cartes
  static const surfaceAlt = Color(0xFF161A22); // orbe anneau externe
  static const surfaceHi = Color(0xFF1F2530); // orbe anneau interne
  static const border = Color(0xFF1E212A); // bordures cartes
  static const borderHi = Color(0xFF23262E); // bordures fortes

  // Fonds clairs (mode bilan / carnet — inversion lumineuse)
  static const cream = Color(0xFFF5F1E8); // fond bilan
  static const creamCard = Color(0xFFFFFDF8); // cartes sur cream
  static const creamBorder = Color(0xFFE5DECB);
  static const inkWarm = Color(0xFF1A1206); // texte sur cream + carte inversée

  // Accents
  static const clay = Color(0xFFE8623D); // couleur de marque, actions, voix
  static const clayLight = Color(0xFFEE7E5C); // cercles décoratifs
  static const clayPale = Color(0xFFF5A183);
  static const clayDark = Color(0xFF4A1B0C); // texte sur fond clay
  static const clayOnCream = Color(0xFFB5502E); // clay lisible sur cream
  static const gold = Color(0xFFD4B36A); // corrections + vocabulaire UNIQUEMENT
  static const goldBg = Color(0xFF2A2113); // fond chip correction
  static const goldBorder = Color(0xFF4A3A1A);
  static const green = Color(0xFF8FB57A); // statut positif, « en direct »
  static const greenCream = Color(0xFF5E8A4A); // vert sur fond cream

  // Textes
  static const textPrimary = Color(0xFFF5F1E8); // sur sombre
  static const textSecondary = Color(0xFFB9BDC7);
  static const textMuted = Color(0xFF7A7E88);
  static const textFaint = Color(0xFF4A4E58); // icônes inactives
  static const textMutedWarm = Color(0xFF8A8272); // muted sur cream
  static const textFaintWarm = Color(0xFFA39A85); // texte barré sur cream

  // Divers
  static const waveformBar = Color(0xFFFFF7F0); // barres de l'orbe vocal
}

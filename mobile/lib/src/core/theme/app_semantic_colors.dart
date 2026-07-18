import 'package:flutter/material.dart';

import 'app_colors.dart';

/// Rôles sémantiques de couleur — l'unique interface couleur des widgets.
///
/// Les widgets ne connaissent QUE des rôles (`accent`, `correction`,
/// `textMuted`…), jamais la palette brute [AppColors]. Ajouter un thème
/// (marque blanche, nouvelle ambiance) = déclarer une nouvelle instance
/// ici, sans toucher au code des écrans.
///
/// Deux instances livrées :
/// - [dark] : mode conversation (défaut) ;
/// - [cream] : mode bilan/carnet (inversion lumineuse narrative).
class AppSemanticColors extends ThemeExtension<AppSemanticColors> {
  const AppSemanticColors({
    required this.background,
    required this.backgroundDeep,
    required this.surface,
    required this.surfaceAlt,
    required this.surfaceHi,
    required this.border,
    required this.borderStrong,
    required this.accent,
    required this.onAccent,
    required this.accentSoft,
    required this.accentFaint,
    required this.correction,
    required this.correctionBg,
    required this.correctionBorder,
    required this.positive,
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.textFaint,
    required this.waveformBar,
  });

  final Color background;
  final Color backgroundDeep;
  final Color surface;
  final Color surfaceAlt;
  final Color surfaceHi;
  final Color border;
  final Color borderStrong;

  /// Couleur de marque : actions, voix. Une seule action primaire par écran.
  final Color accent;

  /// Texte/icône posé sur un fond [accent].
  final Color onAccent;
  final Color accentSoft;
  final Color accentFaint;

  /// RÉSERVÉ aux corrections et au vocabulaire (l'erreur est dorée, jamais
  /// rouge). Ne jamais l'utiliser en décoration.
  final Color correction;
  final Color correctionBg;
  final Color correctionBorder;

  /// Statut positif, « en direct ».
  final Color positive;

  final Color textPrimary;
  final Color textSecondary;
  final Color textMuted;
  final Color textFaint;
  final Color waveformBar;

  static const dark = AppSemanticColors(
    background: AppColors.ink,
    backgroundDeep: AppColors.inkDeep,
    surface: AppColors.surface,
    surfaceAlt: AppColors.surfaceAlt,
    surfaceHi: AppColors.surfaceHi,
    border: AppColors.border,
    borderStrong: AppColors.borderHi,
    accent: AppColors.clay,
    onAccent: AppColors.clayDark,
    accentSoft: AppColors.clayLight,
    accentFaint: AppColors.clayPale,
    correction: AppColors.gold,
    correctionBg: AppColors.goldBg,
    correctionBorder: AppColors.goldBorder,
    positive: AppColors.green,
    textPrimary: AppColors.textPrimary,
    textSecondary: AppColors.textSecondary,
    textMuted: AppColors.textMuted,
    textFaint: AppColors.textFaint,
    waveformBar: AppColors.waveformBar,
  );

  static const cream = AppSemanticColors(
    background: AppColors.cream,
    backgroundDeep: AppColors.cream,
    surface: AppColors.creamCard,
    surfaceAlt: AppColors.creamCard,
    surfaceHi: AppColors.creamCard,
    border: AppColors.creamBorder,
    borderStrong: AppColors.creamBorder,
    accent: AppColors.clayOnCream,
    onAccent: AppColors.cream,
    accentSoft: AppColors.clayLight,
    accentFaint: AppColors.clayPale,
    correction: AppColors.gold,
    correctionBg: AppColors.inkWarm,
    correctionBorder: AppColors.creamBorder,
    positive: AppColors.greenCream,
    textPrimary: AppColors.inkWarm,
    textSecondary: AppColors.textMutedWarm,
    textMuted: AppColors.textMutedWarm,
    textFaint: AppColors.textFaintWarm,
    waveformBar: AppColors.waveformBar,
  );

  @override
  AppSemanticColors copyWith({
    Color? background,
    Color? backgroundDeep,
    Color? surface,
    Color? surfaceAlt,
    Color? surfaceHi,
    Color? border,
    Color? borderStrong,
    Color? accent,
    Color? onAccent,
    Color? accentSoft,
    Color? accentFaint,
    Color? correction,
    Color? correctionBg,
    Color? correctionBorder,
    Color? positive,
    Color? textPrimary,
    Color? textSecondary,
    Color? textMuted,
    Color? textFaint,
    Color? waveformBar,
  }) {
    return AppSemanticColors(
      background: background ?? this.background,
      backgroundDeep: backgroundDeep ?? this.backgroundDeep,
      surface: surface ?? this.surface,
      surfaceAlt: surfaceAlt ?? this.surfaceAlt,
      surfaceHi: surfaceHi ?? this.surfaceHi,
      border: border ?? this.border,
      borderStrong: borderStrong ?? this.borderStrong,
      accent: accent ?? this.accent,
      onAccent: onAccent ?? this.onAccent,
      accentSoft: accentSoft ?? this.accentSoft,
      accentFaint: accentFaint ?? this.accentFaint,
      correction: correction ?? this.correction,
      correctionBg: correctionBg ?? this.correctionBg,
      correctionBorder: correctionBorder ?? this.correctionBorder,
      positive: positive ?? this.positive,
      textPrimary: textPrimary ?? this.textPrimary,
      textSecondary: textSecondary ?? this.textSecondary,
      textMuted: textMuted ?? this.textMuted,
      textFaint: textFaint ?? this.textFaint,
      waveformBar: waveformBar ?? this.waveformBar,
    );
  }

  @override
  AppSemanticColors lerp(ThemeExtension<AppSemanticColors>? other, double t) {
    if (other is! AppSemanticColors) return this;
    Color mix(Color a, Color b) => Color.lerp(a, b, t)!;
    return AppSemanticColors(
      background: mix(background, other.background),
      backgroundDeep: mix(backgroundDeep, other.backgroundDeep),
      surface: mix(surface, other.surface),
      surfaceAlt: mix(surfaceAlt, other.surfaceAlt),
      surfaceHi: mix(surfaceHi, other.surfaceHi),
      border: mix(border, other.border),
      borderStrong: mix(borderStrong, other.borderStrong),
      accent: mix(accent, other.accent),
      onAccent: mix(onAccent, other.onAccent),
      accentSoft: mix(accentSoft, other.accentSoft),
      accentFaint: mix(accentFaint, other.accentFaint),
      correction: mix(correction, other.correction),
      correctionBg: mix(correctionBg, other.correctionBg),
      correctionBorder: mix(correctionBorder, other.correctionBorder),
      positive: mix(positive, other.positive),
      textPrimary: mix(textPrimary, other.textPrimary),
      textSecondary: mix(textSecondary, other.textSecondary),
      textMuted: mix(textMuted, other.textMuted),
      textFaint: mix(textFaint, other.textFaint),
      waveformBar: mix(waveformBar, other.waveformBar),
    );
  }
}

import 'package:flutter/material.dart';

import 'app_semantic_colors.dart';
import 'app_spacing.dart';
import 'app_typography.dart';

export 'app_motion.dart';
export 'app_semantic_colors.dart';
export 'app_spacing.dart';
export 'app_typography.dart';

/// Point d'entrée unique du thème — DESIGN_SPEC §2-§4.
///
/// - [dark] : mode conversation, défaut de toute l'app (on parle le soir).
/// - [light] : mode bilan/carnet — inversion lumineuse narrative, appliqué
///   localement (écran bilan, flashcards) via `Theme(data: AppTheme.light())`.
///
/// Toute la configuration visuelle vit dans `core/theme/` : ajouter un
/// thème = fournir une nouvelle [AppSemanticColors], zéro changement
/// dans les écrans.
abstract final class AppTheme {
  static ThemeData dark() => _build(AppSemanticColors.dark, Brightness.dark);

  static ThemeData light() => _build(AppSemanticColors.cream, Brightness.light);

  static ThemeData _build(AppSemanticColors c, Brightness brightness) {
    final textTheme = _textTheme(c);
    final buttonShape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(AppRadius.card),
    );
    const buttonSize = Size(64, 52);

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      scaffoldBackgroundColor: c.background,
      // Ripples discrets (pas d'InkSparkle — DESIGN_SPEC §4).
      splashFactory: InkRipple.splashFactory,
      colorScheme: _colorScheme(c, brightness),
      textTheme: textTheme,
      extensions: [c],
      appBarTheme: AppBarTheme(
        backgroundColor: c.background,
        foregroundColor: c.textPrimary,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: AppType.displayMd(c.textPrimary),
      ),
      cardTheme: CardThemeData(
        color: c.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.card),
          side: BorderSide(color: c.border, width: AppStroke.hairline),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: c.accent,
          foregroundColor: c.onAccent,
          disabledBackgroundColor: c.surfaceHi,
          disabledForegroundColor: c.textFaint,
          elevation: 0,
          minimumSize: buttonSize,
          shape: buttonShape,
          textStyle: AppType.label(c.onAccent).copyWith(fontSize: 14),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: c.textPrimary,
          disabledForegroundColor: c.textFaint,
          side: BorderSide(color: c.borderStrong, width: AppStroke.hairline),
          minimumSize: buttonSize,
          shape: buttonShape,
          textStyle: AppType.label(c.textPrimary).copyWith(fontSize: 14),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: c.accent,
          disabledForegroundColor: c.textFaint,
          minimumSize: buttonSize,
          shape: buttonShape,
          textStyle: AppType.label(c.accent).copyWith(fontSize: 14),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: c.surface,
        hintStyle: AppType.body(c.textMuted),
        labelStyle: AppType.body(c.textSecondary),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.md,
        ),
        enabledBorder: _inputBorder(c.border),
        focusedBorder: _inputBorder(c.accent),
        errorBorder: _inputBorder(c.accent),
        focusedErrorBorder: _inputBorder(c.accent),
        errorStyle: AppType.label(c.accent),
      ),
      dividerTheme: DividerThemeData(
        color: c.border,
        thickness: AppStroke.hairline,
        space: AppSpacing.xl,
      ),
      iconTheme: IconThemeData(color: c.textSecondary),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: c.accent,
        linearTrackColor: c.surfaceHi,
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: c.surfaceHi,
        contentTextStyle: AppType.body(c.textPrimary),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.card),
        ),
      ),
    );
  }

  /// Jamais de rouge, même pour `error` : la palette n'en contient pas
  /// (DESIGN_SPEC §9) — les erreurs système s'affichent en clay.
  static ColorScheme _colorScheme(AppSemanticColors c, Brightness b) {
    final base = b == Brightness.dark
        ? const ColorScheme.dark()
        : const ColorScheme.light();
    return base.copyWith(
      primary: c.accent,
      onPrimary: c.onAccent,
      secondary: c.accentSoft,
      onSecondary: c.onAccent,
      surface: c.surface,
      onSurface: c.textPrimary,
      surfaceContainerHighest: c.surfaceHi,
      onSurfaceVariant: c.textSecondary,
      outline: c.border,
      outlineVariant: c.borderStrong,
      error: c.accent,
      onError: c.onAccent,
    );
  }

  static TextTheme _textTheme(AppSemanticColors c) => TextTheme(
        displayLarge: AppType.displayXl(c.textPrimary),
        displayMedium: AppType.displayLg(c.textPrimary),
        headlineMedium: AppType.displayLg(c.textPrimary),
        titleLarge: AppType.displayMd(c.textPrimary),
        titleMedium: AppType.displayMd(c.textPrimary),
        bodyLarge: AppType.body(c.textPrimary).copyWith(fontSize: 16),
        bodyMedium: AppType.body(c.textPrimary),
        bodySmall: AppType.body(c.textSecondary).copyWith(fontSize: 12),
        labelLarge: AppType.label(c.textPrimary).copyWith(fontSize: 14),
        labelMedium: AppType.label(c.textPrimary),
        labelSmall: AppType.overline(c.textMuted),
      );

  static OutlineInputBorder _inputBorder(Color color) => OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.card),
        borderSide: BorderSide(color: color, width: AppStroke.hairline),
      );
}

/// Accès raccourci aux rôles sémantiques : `context.colors.accent`.
extension AppThemeContext on BuildContext {
  AppSemanticColors get colors =>
      Theme.of(this).extension<AppSemanticColors>()!;
}

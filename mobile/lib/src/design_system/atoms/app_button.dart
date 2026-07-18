import 'package:flutter/material.dart';

/// Callback de pression — typedef dédié pour rester découplé (OCP).
typedef AppButtonPressed = void Function();

/// Variantes visuelles du bouton. Le style de chaque variante vit dans
/// `core/theme/app_theme.dart` (Filled/Outlined/TextButtonTheme) : ce
/// widget ne contient AUCUNE couleur ni dimension en dur.
enum AppButtonVariant {
  /// Action primaire (clay). Une seule par écran — règle DESIGN_SPEC.
  primary,

  /// Action secondaire (bordure hairline, texte primaire).
  outlined,

  /// Action tertiaire, texte seul (accent).
  ghost,
}

/// Bouton unique du design system.
///
/// Extension sans modification : une nouvelle variante = un nouveau cas
/// dans [AppButtonVariant] + son mapping dans [_buildForVariant] + son
/// style dans le thème — le code des écrans existants ne change jamais.
class AppButton extends StatelessWidget {
  const AppButton.primary({
    super.key,
    required this.label,
    this.onPressed,
    this.icon,
    this.fullWidth = false,
  }) : variant = AppButtonVariant.primary;

  const AppButton.outlined({
    super.key,
    required this.label,
    this.onPressed,
    this.icon,
    this.fullWidth = false,
  }) : variant = AppButtonVariant.outlined;

  const AppButton.ghost({
    super.key,
    required this.label,
    this.onPressed,
    this.icon,
    this.fullWidth = false,
  }) : variant = AppButtonVariant.ghost;

  final String label;
  final AppButtonPressed? onPressed;
  final IconData? icon;
  final bool fullWidth;
  final AppButtonVariant variant;

  @override
  Widget build(BuildContext context) {
    final button = _buildForVariant();
    if (!fullWidth) return button;
    return SizedBox(width: double.infinity, child: button);
  }

  Widget _buildForVariant() {
    final child = Text(label);
    final iconWidget = icon == null ? null : Icon(icon);
    return switch (variant) {
      AppButtonVariant.primary => iconWidget == null
          ? FilledButton(onPressed: onPressed, child: child)
          : FilledButton.icon(
              onPressed: onPressed, icon: iconWidget, label: child),
      AppButtonVariant.outlined => iconWidget == null
          ? OutlinedButton(onPressed: onPressed, child: child)
          : OutlinedButton.icon(
              onPressed: onPressed, icon: iconWidget, label: child),
      AppButtonVariant.ghost => iconWidget == null
          ? TextButton(onPressed: onPressed, child: child)
          : TextButton.icon(
              onPressed: onPressed, icon: iconWidget, label: child),
    };
  }
}

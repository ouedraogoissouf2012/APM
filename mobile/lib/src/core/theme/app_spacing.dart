/// Espacements — échelle unique de l'app (multiples de 4).
abstract final class AppSpacing {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;
}

/// Rayons — contrat DESIGN_SPEC §4.
abstract final class AppRadius {
  static const double chip = 10; // chips / petits éléments
  static const double card = 14; // cartes standard (13–15)
  static const double hero = 18; // cartes hero (17–18)
  static const double pill = 20; // pills / statuts
  static const double device = 24; // conteneurs plein écran
}

/// Traits — profondeur par superposition de surfaces, jamais d'ombre.
abstract final class AppStroke {
  static const double hairline = 1;
}

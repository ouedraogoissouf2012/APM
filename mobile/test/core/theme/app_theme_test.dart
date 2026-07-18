import 'package:apm/src/core/theme/app_colors.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  // google_fonts consulte le manifeste d'assets dès la création d'un
  // TextStyle : le binding de test doit exister (cf. doc google_fonts).
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AppColors — contrat DESIGN_SPEC (valeurs hex exactes)', () {
    test('fonds sombres', () {
      expect(AppColors.ink, const Color(0xFF0D0F15));
      expect(AppColors.inkDeep, const Color(0xFF08090D));
      expect(AppColors.surface, const Color(0xFF13161D));
      expect(AppColors.surfaceAlt, const Color(0xFF161A22));
      expect(AppColors.surfaceHi, const Color(0xFF1F2530));
      expect(AppColors.border, const Color(0xFF1E212A));
    });

    test('fonds clairs (mode bilan)', () {
      expect(AppColors.cream, const Color(0xFFF5F1E8));
      expect(AppColors.creamCard, const Color(0xFFFFFDF8));
      expect(AppColors.inkWarm, const Color(0xFF1A1206));
    });

    test('accents', () {
      expect(AppColors.clay, const Color(0xFFE8623D));
      expect(AppColors.gold, const Color(0xFFD4B36A));
      expect(AppColors.goldBg, const Color(0xFF2A2113));
      expect(AppColors.green, const Color(0xFF8FB57A));
    });
  });

  group('AppType — typographie DESIGN_SPEC', () {
    test('display en Fraunces, UI en Inter', () {
      expect(AppType.displayXl(AppColors.textPrimary).fontFamily,
          contains('Fraunces'));
      expect(AppType.transcript(AppColors.textPrimary).fontFamily,
          contains('Fraunces'));
      expect(AppType.body(AppColors.textPrimary).fontFamily, contains('Inter'));
      expect(
          AppType.overline(AppColors.textMuted).fontFamily, contains('Inter'));
    });

    test('jamais de graisse 600+ (règle stricte)', () {
      final styles = [
        AppType.displayXl(AppColors.textPrimary),
        AppType.displayLg(AppColors.textPrimary),
        AppType.displayMd(AppColors.textPrimary),
        AppType.transcript(AppColors.textPrimary),
        AppType.body(AppColors.textPrimary),
        AppType.label(AppColors.textPrimary),
        AppType.overline(AppColors.textPrimary),
      ];
      for (final s in styles) {
        final weight = s.fontWeight ?? FontWeight.w400;
        expect(weight.index, lessThanOrEqualTo(FontWeight.w500.index),
            reason: 'graisse interdite: $weight');
      }
    });

    test('transcript = italique light 19', () {
      final s = AppType.transcript(AppColors.textPrimary);
      expect(s.fontSize, 19);
      expect(s.fontStyle, FontStyle.italic);
      expect(s.fontWeight, FontWeight.w300);
    });

    test('overline = 11px avec letter-spacing marqué', () {
      final s = AppType.overline(AppColors.textMuted);
      expect(s.fontSize, 11);
      expect(s.letterSpacing, 1.2);
    });
  });

  group('AppTheme.dark — mode conversation (défaut)', () {
    test('scaffold = ink, Material 3, extension sémantique exposée', () {
      final theme = AppTheme.dark();
      expect(theme.scaffoldBackgroundColor, AppColors.ink);
      expect(theme.useMaterial3, isTrue);
      final colors = theme.extension<AppSemanticColors>();
      expect(colors, isNotNull);
      expect(colors!.accent, AppColors.clay);
      expect(colors.correction, AppColors.gold);
      expect(colors.textPrimary, AppColors.textPrimary);
    });

    test('pas d\'élévation Material (profondeur = surfaces superposées)', () {
      final theme = AppTheme.dark();
      expect(theme.cardTheme.elevation, 0);
      expect(theme.appBarTheme.elevation, 0);
      final filled = theme.filledButtonTheme.style!;
      expect(filled.elevation?.resolve({}), 0);
    });

    test('bouton primaire = clay avec texte clayDark', () {
      final style = AppTheme.dark().filledButtonTheme.style!;
      expect(style.backgroundColor?.resolve({}), AppColors.clay);
      expect(style.foregroundColor?.resolve({}), AppColors.clayDark);
    });
  });

  group('AppTheme.light — mode bilan (inversion cream)', () {
    test('scaffold = cream, textes chauds', () {
      final theme = AppTheme.light();
      expect(theme.scaffoldBackgroundColor, AppColors.cream);
      final colors = theme.extension<AppSemanticColors>()!;
      expect(colors.textPrimary, AppColors.inkWarm);
      expect(colors.accent, AppColors.clayOnCream);
      expect(colors.positive, AppColors.greenCream);
    });
  });

  group('AppSemanticColors — extension thème', () {
    test('lerp interpole entre dark et cream', () {
      final mid = AppSemanticColors.dark
          .lerp(AppSemanticColors.cream, 0.5);
      expect(mid.background, isNot(AppColors.ink));
      expect(mid.background, isNot(AppColors.cream));
    });

    test('copyWith remplace uniquement les champs fournis', () {
      final copy =
          AppSemanticColors.dark.copyWith(accent: AppColors.gold);
      expect(copy.accent, AppColors.gold);
      expect(copy.background, AppSemanticColors.dark.background);
    });
  });

  group('Tokens de forme et de motion', () {
    test('rayons DESIGN_SPEC', () {
      expect(AppRadius.chip, 10);
      expect(AppRadius.card, 14);
      expect(AppRadius.hero, 18);
      expect(AppRadius.pill, 20);
    });

    test('durées DESIGN_SPEC', () {
      expect(AppMotion.chipEntrance, const Duration(milliseconds: 250));
      expect(AppMotion.chipDelay, const Duration(milliseconds: 400));
      expect(AppMotion.inversion, const Duration(milliseconds: 450));
      expect(AppMotion.orbRing, const Duration(milliseconds: 2400));
      expect(AppMotion.waveform, const Duration(milliseconds: 1100));
    });
  });
}

import 'package:apm/src/core/theme/app_colors.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/design_system/molecules/correction_chip.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _harness(Widget child, {bool disableAnimations = false}) => MaterialApp(
      theme: AppTheme.dark(),
      home: MediaQuery(
        data: MediaQueryData(disableAnimations: disableAnimations),
        child: Scaffold(body: Center(child: child)),
      ),
    );

void main() {
  testWidgets('affiche la faute barrée, la flèche et la correction en gold',
      (tester) async {
    await tester.pumpWidget(_harness(
      const CorrectionChip(original: 'I have 25 years', corrected: 'I am 25'),
    ));
    await tester.pump(AppMotion.chipDelay + AppMotion.chipEntrance);

    final richText = tester.widget<Text>(find.byKey(
      const Key('correction_chip_text'),
    ));
    final span = richText.textSpan! as TextSpan;
    final children = span.children!.cast<TextSpan>();

    expect(children[0].text, 'I have 25 years');
    expect(children[0].style?.decoration, TextDecoration.lineThrough);
    expect(children[1].text, ' → ');
    expect(children[2].text, 'I am 25');
    expect(children[2].style?.color, AppColors.gold);
  });

  testWidgets(
      'non-interruption : invisible avant le délai de 400ms, visible après',
      (tester) async {
    await tester.pumpWidget(_harness(
      const CorrectionChip(original: 'a', corrected: 'b'),
    ));

    final fade = tester.widget<FadeTransition>(
      find.byKey(const Key('correction_chip_fade')),
    );
    expect(fade.opacity.value, 0.0, reason: 'invisible pendant le délai');

    await tester.pump(AppMotion.chipDelay);
    await tester.pump(AppMotion.chipEntrance);
    expect(fade.opacity.value, 1.0, reason: 'visible après délai + entrée');
  });

  testWidgets('accessibilité : apparition immédiate si animations désactivées',
      (tester) async {
    await tester.pumpWidget(_harness(
      const CorrectionChip(original: 'a', corrected: 'b'),
      disableAnimations: true,
    ));
    await tester.pump();

    final fade = tester.widget<FadeTransition>(
      find.byKey(const Key('correction_chip_fade')),
    );
    expect(fade.opacity.value, 1.0);
  });

  testWidgets('icône sparkles présente (l\'erreur est précieuse)',
      (tester) async {
    await tester.pumpWidget(_harness(
      const CorrectionChip(original: 'a', corrected: 'b'),
    ));
    await tester.pump(AppMotion.chipDelay + AppMotion.chipEntrance);
    expect(find.byIcon(Icons.auto_awesome), findsOneWidget);
  });
}

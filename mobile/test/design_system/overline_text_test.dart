import 'package:apm/src/core/theme/app_colors.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/design_system/atoms/overline_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _harness(Widget child) => MaterialApp(
      theme: AppTheme.dark(),
      home: Scaffold(body: Center(child: child)),
    );

void main() {
  testWidgets('force les MAJUSCULES quel que soit le texte fourni',
      (tester) async {
    await tester.pumpWidget(_harness(const OverlineText('je t\'écoute')));
    expect(find.text('JE T\'ÉCOUTE'), findsOneWidget);
    expect(find.text('je t\'écoute'), findsNothing);
  });

  testWidgets('style overline : 11px, letter-spacing 1.2, textMuted par défaut',
      (tester) async {
    await tester.pumpWidget(_harness(const OverlineText('mémoire')));
    final text = tester.widget<Text>(find.text('MÉMOIRE'));
    expect(text.style?.fontSize, 11);
    expect(text.style?.letterSpacing, 1.2);
    expect(text.style?.color, AppColors.textMuted);
  });

  testWidgets('couleur personnalisable (ex. catégorie TON COMBAT en gold)',
      (tester) async {
    await tester.pumpWidget(_harness(
      const OverlineText('ton combat', color: AppColors.gold),
    ));
    final text = tester.widget<Text>(find.text('TON COMBAT'));
    expect(text.style?.color, AppColors.gold);
  });
}

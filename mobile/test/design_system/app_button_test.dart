import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/design_system/atoms/app_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _harness(Widget child) => MaterialApp(
      theme: AppTheme.dark(),
      home: Scaffold(body: Center(child: child)),
    );

void main() {
  testWidgets('primary rend un FilledButton stylé par le thème',
      (tester) async {
    var pressed = false;
    await tester.pumpWidget(_harness(
      AppButton.primary(label: 'Commencer', onPressed: () => pressed = true),
    ));

    expect(find.byType(FilledButton), findsOneWidget);
    expect(find.text('Commencer'), findsOneWidget);
    await tester.tap(find.byType(AppButton));
    expect(pressed, isTrue);
  });

  testWidgets('outlined rend un OutlinedButton', (tester) async {
    await tester.pumpWidget(_harness(
      AppButton.outlined(label: 'Encore', onPressed: () {}),
    ));
    expect(find.byType(OutlinedButton), findsOneWidget);
  });

  testWidgets('ghost rend un TextButton', (tester) async {
    await tester.pumpWidget(_harness(
      AppButton.ghost(label: 'Passer', onPressed: () {}),
    ));
    expect(find.byType(TextButton), findsOneWidget);
  });

  testWidgets('onPressed null désactive le bouton', (tester) async {
    await tester.pumpWidget(_harness(
      const AppButton.primary(label: 'Inactif'),
    ));
    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button.enabled, isFalse);
  });

  testWidgets('icône optionnelle affichée avant le label', (tester) async {
    await tester.pumpWidget(_harness(
      AppButton.primary(label: 'Parler', icon: Icons.mic, onPressed: () {}),
    ));
    expect(find.byIcon(Icons.mic), findsOneWidget);
    expect(find.text('Parler'), findsOneWidget);
  });

  testWidgets('fullWidth étire le bouton sur la largeur disponible',
      (tester) async {
    await tester.pumpWidget(_harness(
      SizedBox(
        width: 300,
        child: AppButton.primary(
            label: 'Large', fullWidth: true, onPressed: () {}),
      ),
    ));
    final size = tester.getSize(find.byType(FilledButton));
    expect(size.width, 300);
  });
}

import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/design_system/molecules/transcript_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _harness(Widget child) => MaterialApp(
      theme: AppTheme.dark(),
      home: Scaffold(body: Center(child: child)),
    );

void main() {
  testWidgets('encadre le texte de guillemets français', (tester) async {
    await tester.pumpWidget(_harness(
      const TranscriptText('I went to the market', listening: false),
    ));
    expect(find.textContaining('« I went to the market »'), findsOneWidget);
  });

  testWidgets('style transcript : Fraunces italique 19', (tester) async {
    await tester.pumpWidget(_harness(
      const TranscriptText('Hello', listening: false),
    ));
    final text =
        tester.widget<Text>(find.byKey(const Key('transcript_text')));
    expect(text.style?.fontFamily, 'Fraunces');
    expect(text.style?.fontSize, 19);
    expect(text.style?.fontStyle, FontStyle.italic);
  });

  testWidgets('curseur clignotant visible uniquement en écoute',
      (tester) async {
    await tester.pumpWidget(_harness(
      const TranscriptText('Hello', listening: true),
    ));
    expect(find.byKey(const Key('transcript_cursor')), findsOneWidget);

    await tester.pumpWidget(_harness(
      const TranscriptText('Hello', listening: false),
    ));
    expect(find.byKey(const Key('transcript_cursor')), findsNothing);
  });

  testWidgets('le curseur alterne visible/invisible (blink 1s en steps)',
      (tester) async {
    await tester.pumpWidget(_harness(
      const TranscriptText('Hello', listening: true),
    ));

    double opacityNow() => tester
        .widget<Opacity>(find.byKey(const Key('transcript_cursor_opacity')))
        .opacity;

    final first = opacityNow();
    await tester.pump(const Duration(milliseconds: 500));
    final second = opacityNow();
    expect(first, isNot(second), reason: 'doit alterner en 500ms');
  });
}

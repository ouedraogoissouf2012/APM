import 'package:apm/src/data/models/debrief.dart';
import 'package:apm/src/ui/debrief/widgets/pronunciation_map.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  testWidgets('shows a chip for each reliable score', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const PronunciationMap(
          scores: [
            PronunciationScore(word: 'hello', score: 0.9, confidence: 0.9),
            PronunciationScore(word: 'world', score: 0.5, confidence: 0.9),
          ],
        ),
      ),
    );

    expect(find.byKey(const Key('pronunciation_hello_word')), findsOneWidget);
    expect(find.byKey(const Key('pronunciation_world_word')), findsOneWidget);
    expect(find.byKey(const Key('pronunciation_empty')), findsNothing);
  });

  testWidgets('shows the empty message when no score is reliable', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const PronunciationMap(
          scores: [PronunciationScore(word: 'hello', confidence: 0.9)], // no score
        ),
      ),
    );

    expect(find.byKey(const Key('pronunciation_empty')), findsOneWidget);
  });

  testWidgets('notes when some words were skipped for low confidence', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const PronunciationMap(
          scores: [
            PronunciationScore(word: 'ok', score: 0.9, confidence: 0.9),
            PronunciationScore(word: 'meh', score: 0.9, confidence: 0.2),
          ],
        ),
      ),
    );

    expect(find.byKey(const Key('pronunciation_uncertain_note')), findsOneWidget);
  });

  testWidgets('never shows a fake "Perfect" when there is no score', (tester) async {
    await tester.pumpWidget(
      _wrap(const PronunciationMap(scores: [PronunciationScore(word: 'hello')])),
    );

    expect(find.textContaining('Perfect'), findsNothing);
    expect(find.byKey(const Key('pronunciation_empty')), findsOneWidget);
  });
}

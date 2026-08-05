import 'package:apm/src/data/models/vocabulary_entry.dart';
import 'package:apm/src/data/repositories/vocabulary_repository.dart';
import 'package:apm/src/ui/vocabulary/view_model/vocabulary_view_model.dart';
import 'package:apm/src/ui/vocabulary/widgets/vocabulary_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockVocabRepo extends Mock implements VocabularyRepository {}

VocabularyEntry _entry() => const VocabularyEntry(
  id: 1,
  sessionId: 23,
  word: 'deployment',
  phonetic: 'dɪˈplɔɪmənt',
  translation: 'déploiement',
  example: 'I handle deployments at work.',
  status: 'review',
);

Future<void> _pump(WidgetTester tester, VocabularyRepository repo) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [vocabularyRepositoryProvider.overrideWithValue(repo)],
      child: const MaterialApp(home: VocabularyScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('renders a WordCard with the learner sentence', (tester) async {
    final repo = _MockVocabRepo();
    when(repo.list).thenAnswer((_) async => [_entry()]);

    await _pump(tester, repo);

    expect(find.text('deployment'), findsOneWidget);
    expect(find.textContaining('VU EN SESSION #23'), findsOneWidget);
    expect(find.textContaining('I handle deployments at work.'), findsOneWidget);
    expect(find.text('Encore'), findsOneWidget);
    expect(find.text('Je le sais'), findsOneWidget);
  });

  testWidgets('empty notebook shows a friendly hint', (tester) async {
    final repo = _MockVocabRepo();
    when(repo.list).thenAnswer((_) async => <VocabularyEntry>[]);

    await _pump(tester, repo);

    expect(find.byKey(const Key('vocab_empty')), findsOneWidget);
  });

  testWidgets('tapping "Je le sais" marks the card known', (tester) async {
    final repo = _MockVocabRepo();
    when(repo.list).thenAnswer((_) async => [_entry()]);
    when(
      () => repo.setStatus(any(), any()),
    ).thenAnswer((_) async => _entry().copyWith(status: 'known'));

    await _pump(tester, repo);
    await tester.tap(find.byKey(const Key('vocab_known_1')));
    await tester.pumpAndSettle();

    verify(() => repo.setStatus(1, 'known')).called(1);
  });

  testWidgets('error state shows a message', (tester) async {
    final repo = _MockVocabRepo();
    when(repo.list).thenThrow(Exception('down'));

    await _pump(tester, repo);

    expect(find.byKey(const Key('vocab_error')), findsOneWidget);
  });
}

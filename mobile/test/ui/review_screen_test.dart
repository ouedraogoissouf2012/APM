import 'package:apm/src/data/models/review_item.dart';
import 'package:apm/src/data/repositories/review_repository.dart';
import 'package:apm/src/ui/review/error_type_label.dart';
import 'package:apm/src/ui/review/view_model/review_view_model.dart';
import 'package:apm/src/ui/review/widgets/review_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockReviewRepo extends Mock implements ReviewRepository {}

ReviewItem _item({String type = 'verb_tense', int streak = 1}) => ReviewItem(
  errorType: type,
  latestCorrection: 'I went',
  stage: 1,
  cleanStreak: streak,
  status: 'due',
);

Future<void> _pump(WidgetTester tester, ReviewRepository repo) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [reviewRepositoryProvider.overrideWithValue(repo)],
      child: const MaterialApp(home: ReviewScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('errorTypeLabel', () {
    test('maps known types to French labels', () {
      expect(errorTypeLabel('verb_tense'), 'Temps du verbe');
      expect(errorTypeLabel('article'), 'Articles');
    });

    test('humanises an unknown type instead of showing a raw slug', () {
      expect(errorTypeLabel('some_new_type'), 'Some new type');
      expect(errorTypeLabel(''), 'Divers');
    });
  });

  testWidgets('lists due items with a human label and the correction', (
    tester,
  ) async {
    final repo = _MockReviewRepo();
    when(repo.dueItems).thenAnswer((_) async => [_item()]);

    await _pump(tester, repo);

    expect(find.text('Temps du verbe'), findsOneWidget);
    expect(find.textContaining('I went'), findsOneWidget);
    expect(find.textContaining('1 / 3 sessions'), findsOneWidget);
    expect(find.byKey(const Key('review_practice_button')), findsOneWidget);
  });

  testWidgets('empty queue shows a celebratory hint, no practice button', (
    tester,
  ) async {
    final repo = _MockReviewRepo();
    when(repo.dueItems).thenAnswer((_) async => <ReviewItem>[]);

    await _pump(tester, repo);

    expect(find.byKey(const Key('review_empty')), findsOneWidget);
    expect(find.byKey(const Key('review_practice_button')), findsNothing);
  });

  testWidgets('error state shows a message', (tester) async {
    final repo = _MockReviewRepo();
    when(repo.dueItems).thenThrow(Exception('down'));

    await _pump(tester, repo);

    expect(find.byKey(const Key('review_error')), findsOneWidget);
  });
}

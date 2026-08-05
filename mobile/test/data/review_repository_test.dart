import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/review_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  test('dueItems parses the review queue', () async {
    final api = _MockApiClient();
    when(() => api.getList('/me/review')).thenAnswer(
      (_) async => [
        {
          'error_type': 'verb_tense',
          'latest_correction': 'I went',
          'stage': 1,
          'clean_streak': 1,
          'status': 'due',
          'next_review_at': '2026-08-06T12:00:00Z',
        },
      ],
    );

    final items = await ReviewRepository(api).dueItems();
    expect(items, hasLength(1));
    expect(items.single.errorType, 'verb_tense');
    expect(items.single.latestCorrection, 'I went');
    expect(items.single.cleanStreak, 1);
    expect(items.single.nextReviewAt, isNotNull);
  });

  test('handles a null next_review_at and missing fields', () async {
    final api = _MockApiClient();
    when(() => api.getList('/me/review')).thenAnswer(
      (_) async => [
        {'error_type': 'article', 'status': 'due', 'next_review_at': null},
      ],
    );

    final items = await ReviewRepository(api).dueItems();
    expect(items.single.nextReviewAt, isNull);
    expect(items.single.latestCorrection, '');
    expect(items.single.cleanStreak, 0);
  });
}

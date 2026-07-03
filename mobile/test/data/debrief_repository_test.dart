import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/data/repositories/debrief_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  test(
    'generate posts to the debrief endpoint and parses the result',
    () async {
      final api = _MockApiClient();
      when(() => api.postJson('/sessions/3/debrief')).thenAnswer(
        (_) async => {
          'session_id': 3,
          'cefr_estimate': 'A2',
          'summary': 'ok',
          'errors': [
            {
              'original': 'x',
              'correction': 'y',
              'rule': 'r',
              'error_type': 't',
            },
          ],
        },
      );
      final repo = DebriefRepository(api);

      final debrief = await repo.generate(3);

      expect(debrief.cefrEstimate, 'A2');
      expect(debrief.errors.single.correction, 'y');
    },
  );

  test('getOrGenerate returns an existing debrief without posting', () async {
    final api = _MockApiClient();
    when(() => api.getJson('/sessions/3/debrief')).thenAnswer(
      (_) async => {
        'session_id': 3,
        'cefr_estimate': 'B1',
        'summary': 'cached',
        'errors': [],
      },
    );
    final repo = DebriefRepository(api);

    final debrief = await repo.getOrGenerate(3);

    expect(debrief.summary, 'cached');
    verifyNever(() => api.postJson('/sessions/3/debrief'));
  });

  test('getOrGenerate posts when no debrief exists yet', () async {
    final api = _MockApiClient();
    when(() => api.getJson('/sessions/3/debrief')).thenThrow(
      const ApiException(
        statusCode: 404,
        code: 'NotFoundError',
        message: 'missing',
      ),
    );
    when(() => api.postJson('/sessions/3/debrief')).thenAnswer(
      (_) async => {
        'session_id': 3,
        'cefr_estimate': 'A2',
        'summary': 'new',
        'errors': [],
      },
    );
    final repo = DebriefRepository(api);

    final debrief = await repo.getOrGenerate(3);

    expect(debrief.summary, 'new');
    verify(() => api.postJson('/sessions/3/debrief')).called(1);
  });
}

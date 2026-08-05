import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/proof_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  late _MockApiClient api;
  late ProofRepository repo;

  setUp(() {
    api = _MockApiClient();
    repo = ProofRepository(api);
  });

  test('parses the proof delta', () async {
    when(() => api.getJson('/me/proof/job_interview')).thenAnswer(
      (_) async => {
        'skill': 'job_interview',
        'baseline_session_id': 1,
        'latest_session_id': 2,
        'baseline_started_at': '2026-08-01T10:00:00Z',
        'latest_started_at': '2026-08-05T10:00:00Z',
        'baseline_cefr': 'A2',
        'latest_cefr': 'B1',
        'resolved': ['verb_tense'],
        'new_or_worse': <String>[],
      },
    );

    final proof = await repo.forSkill('job_interview');
    expect(proof, isNotNull);
    expect(proof!.baselineCefr, 'A2');
    expect(proof.latestCefr, 'B1');
    expect(proof.resolved, ['verb_tense']);
  });

  test('returns null when there is not enough history (404)', () async {
    when(() => api.getJson('/me/proof/restaurant')).thenThrow(
      const ApiException(statusCode: 404, code: 'NotFound', message: 'not yet'),
    );

    final proof = await repo.forSkill('restaurant');
    expect(proof, isNull);
  });

  test('transferChallenge posts and parses the compiled mission', () async {
    when(() => api.postJson('/me/transfer/job_interview')).thenAnswer(
      (_) async => {
        'id': 42,
        'source_type': 'topic',
        'persona': 'A surprise interlocutor',
        'goal': 'Handle a new situation',
        'likely_questions': <String>[],
      },
    );

    final mission = await repo.transferChallenge('job_interview');
    expect(mission.id, 42);
    expect(mission.persona, 'A surprise interlocutor');
  });
}

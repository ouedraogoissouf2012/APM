import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/vocabulary_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  late _MockApiClient api;
  late VocabularyRepository repo;

  setUp(() {
    api = _MockApiClient();
    repo = VocabularyRepository(api);
  });

  test('list parses the notebook entries', () async {
    when(() => api.getList('/vocabulary')).thenAnswer(
      (_) async => [
        {
          'id': 1,
          'session_id': 23,
          'word': 'deployment',
          'phonetic': 'dɪˈplɔɪmənt',
          'translation': 'déploiement',
          'example': 'I handle deployments at work.',
          'status': 'review',
        },
      ],
    );

    final entries = await repo.list();
    expect(entries, hasLength(1));
    expect(entries.single.word, 'deployment');
    expect(entries.single.sessionId, 23);
    expect(entries.single.isKnown, isFalse);
  });

  test('setStatus PATCHes the status and parses the result', () async {
    Map<String, dynamic>? sentBody;
    when(
      () => api.patchJson('/vocabulary/1', body: any(named: 'body')),
    ).thenAnswer((invocation) async {
      sentBody = invocation.namedArguments[#body] as Map<String, dynamic>;
      return {
        'id': 1,
        'session_id': null,
        'word': 'handle',
        'phonetic': '',
        'translation': '',
        'example': '',
        'status': 'known',
      };
    });

    final updated = await repo.setStatus(1, 'known');
    expect(sentBody!['status'], 'known');
    expect(updated.isKnown, isTrue);
  });
}

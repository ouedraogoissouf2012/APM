import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/models/mission.dart';
import 'package:apm/src/data/repositories/mission_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  late _MockApiClient api;
  late MissionRepository repo;

  setUp(() {
    api = _MockApiClient();
    repo = MissionRepository(api);
  });

  test('compile posts source_type + content and parses the brief', () async {
    Map<String, dynamic>? sentBody;
    when(() => api.postJson('/missions', body: any(named: 'body'))).thenAnswer((
      invocation,
    ) async {
      sentBody = invocation.namedArguments[#body] as Map<String, dynamic>;
      return {
        'id': 7,
        'source_type': 'offer',
        'persona': 'A recruiter for a backend role',
        'goal': 'Pass a first-round screening',
        'likely_questions': ['Tell me about yourself', 'Why this company?'],
      };
    });

    final mission = await repo.compile(
      sourceType: MissionSourceType.offer,
      content: 'Senior backend engineer, Python, ...',
    );

    expect(sentBody!['source_type'], 'offer');
    expect(sentBody!['content'], 'Senior backend engineer, Python, ...');
    expect(mission.id, 7);
    expect(mission.persona, 'A recruiter for a backend role');
    expect(mission.likelyQuestions, hasLength(2));
  });

  test('get fetches a mission by id', () async {
    when(() => api.getJson('/missions/7')).thenAnswer(
      (_) async => {
        'id': 7,
        'source_type': 'cv',
        'persona': 'x',
        'goal': 'y',
        'likely_questions': <String>[],
      },
    );
    final mission = await repo.get(7);
    expect(mission.sourceType, 'cv');
    expect(mission.likelyQuestions, isEmpty);
  });
}

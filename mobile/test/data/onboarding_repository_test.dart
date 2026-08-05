import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/onboarding_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  late _MockApiClient api;
  late OnboardingRepository repo;

  setUp(() {
    api = _MockApiClient();
    repo = OnboardingRepository(api);
  });

  test('submitPlacement posts answers/interests/goal and parses the result', () async {
    Map<String, dynamic>? sentBody;
    when(
      () => api.postJson('/onboarding/placement', body: any(named: 'body')),
    ).thenAnswer((invocation) async {
      sentBody = invocation.namedArguments[#body] as Map<String, dynamic>;
      return {
        'cefr_level': 'B1',
        'interests': ['football'],
        'goal': 'job interview',
      };
    });

    final result = await repo.submitPlacement(
      answers: ['I like sports.'],
      interests: ['football'],
      goal: 'job interview',
    );

    expect(sentBody!['answers'], ['I like sports.']);
    expect(sentBody!['interests'], ['football']);
    expect(sentBody!['goal'], 'job interview');
    expect(result.cefrLevel, 'B1');
    expect(result.interests, ['football']);
    expect(result.goal, 'job interview');
  });

  test('parses an empty goal safely', () async {
    when(
      () => api.postJson('/onboarding/placement', body: any(named: 'body')),
    ).thenAnswer(
      (_) async => {
        'cefr_level': 'A1',
        'interests': <String>[],
        'goal': null,
      },
    );

    final result = await repo.submitPlacement(
      answers: const [],
      interests: const [],
      goal: '',
    );

    expect(result.cefrLevel, 'A1');
    expect(result.goal, '');
    expect(result.interests, isEmpty);
  });
}

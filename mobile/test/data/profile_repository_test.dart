import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/profile_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  late _MockApiClient api;
  late ProfileRepository repo;

  setUp(() {
    api = _MockApiClient();
    repo = ProfileRepository(api);
  });

  test('getProfile fetches and parses the profile', () async {
    when(() => api.getJson('/me/profile')).thenAnswer(
      (_) async => {
        'interests': ['football'],
        'goal': 'job interview',
        'correction_intensity': 'gentle',
        'accent': 'uk',
      },
    );

    final profile = await repo.getProfile();

    expect(profile.interests, ['football']);
    expect(profile.goal, 'job interview');
    expect(profile.accent, 'uk');
  });

  test('getProfile parses memory_summary (and defaults to empty)', () async {
    when(() => api.getJson('/me/profile')).thenAnswer(
      (_) async => {
        'interests': <String>[],
        'goal': null,
        'correction_intensity': 'gentle',
        'accent': 'us',
        'memory_summary': 'Prepares for a UK job interview.',
      },
    );

    final profile = await repo.getProfile();
    expect(profile.memorySummary, 'Prepares for a UK job interview.');
  });

  test('updateProfile sends memory_summary (including empty to clear it)', () async {
    Map<String, dynamic>? sentBody;
    when(() => api.putJson('/me/profile', body: any(named: 'body'))).thenAnswer((
      invocation,
    ) async {
      sentBody = invocation.namedArguments[#body] as Map<String, dynamic>;
      return {
        'interests': <String>[],
        'goal': null,
        'correction_intensity': 'gentle',
        'accent': 'us',
        'memory_summary': '',
      };
    });

    final profile = await repo.updateProfile(memorySummary: '');

    expect(sentBody!['memory_summary'], '');
    expect(profile.memorySummary, '');
  });

  test('updateProfile puts the changes and parses the result', () async {
    when(() => api.putJson('/me/profile', body: any(named: 'body'))).thenAnswer(
      (_) async => {
        'interests': ['cooking'],
        'goal': null,
        'correction_intensity': 'detailed',
        'accent': 'us',
      },
    );

    final profile = await repo.updateProfile(
      interests: ['cooking'],
      correctionIntensity: 'detailed',
      accent: 'us',
    );

    expect(profile.correctionIntensity, 'detailed');
    expect(profile.goal, isNull);
  });
}

import 'package:apm/src/core/network/api_client.dart';
import 'package:apm/src/core/storage/token_storage.dart';
import 'package:apm/src/data/repositories/debrief_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements ApiClient {}

class _Storage implements TokenStorage {
  @override
  Future<void> save({required String accessToken, required String refreshToken}) async {}
  @override
  Future<String?> readAccessToken() async => 'tok';
  @override
  Future<String?> readRefreshToken() async => 'r';
  @override
  Future<void> clear() async {}
}

void main() {
  test('generate posts to the debrief endpoint and parses the result', () async {
    final api = _MockApiClient();
    when(() => api.postJson('/sessions/3/debrief', bearer: any(named: 'bearer'))).thenAnswer(
      (_) async => {
        'session_id': 3,
        'cefr_estimate': 'A2',
        'summary': 'ok',
        'errors': [
          {'original': 'x', 'correction': 'y', 'rule': 'r', 'error_type': 't'},
        ],
      },
    );
    final repo = DebriefRepository(api, _Storage());

    final debrief = await repo.generate(3);

    expect(debrief.cefrEstimate, 'A2');
    expect(debrief.errors.single.correction, 'y');
  });
}

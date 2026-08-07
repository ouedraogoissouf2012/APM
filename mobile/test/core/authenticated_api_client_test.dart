import 'package:apm/src/core/network/api_client.dart';
import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/core/storage/token_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements ApiClient {}

class _InMemoryTokenStorage implements TokenStorage {
  String? access = 'old-access';
  String? refresh = 'old-refresh';

  @override
  Future<void> save({
    required String accessToken,
    required String refreshToken,
  }) async {
    access = accessToken;
    refresh = refreshToken;
  }

  @override
  Future<String?> readAccessToken() async => access;

  @override
  Future<String?> readRefreshToken() async => refresh;

  @override
  Future<void> clear() async {
    access = null;
    refresh = null;
  }
}

void main() {
  test(
    'refreshes tokens and retries once after an authenticated 401',
    () async {
      final api = _MockApiClient();
      final storage = _InMemoryTokenStorage();
      final client = AuthenticatedApiClient(api, storage);

      when(() => api.getJson('/me/profile', bearer: 'old-access')).thenThrow(
        const ApiException(
          statusCode: 401,
          code: 'AuthenticationError',
          message: 'expired',
        ),
      );
      when(
        () => api.postJson(
          '/auth/refresh',
          body: {'refresh_token': 'old-refresh'},
        ),
      ).thenAnswer(
        (_) async => {
          'access_token': 'new-access',
          'refresh_token': 'new-refresh',
        },
      );
      when(() => api.getJson('/me/profile', bearer: 'new-access')).thenAnswer(
        (_) async => {
          'interests': ['football'],
          'goal': null,
          'correction_intensity': 'gentle',
          'accent': 'us',
        },
      );

      final json = await client.getJson('/me/profile');

      expect(json['interests'], ['football']);
      expect(storage.access, 'new-access');
      expect(storage.refresh, 'new-refresh');
      verify(() => api.getJson('/me/profile', bearer: 'old-access')).called(1);
      verify(() => api.getJson('/me/profile', bearer: 'new-access')).called(1);
    },
  );

  test('clears tokens when refresh fails', () async {
    final api = _MockApiClient();
    final storage = _InMemoryTokenStorage();
    final client = AuthenticatedApiClient(api, storage);

    when(() => api.getJson('/me/profile', bearer: 'old-access')).thenThrow(
      const ApiException(
        statusCode: 401,
        code: 'AuthenticationError',
        message: 'expired',
      ),
    );
    when(
      () =>
          api.postJson('/auth/refresh', body: {'refresh_token': 'old-refresh'}),
    ).thenThrow(
      const ApiException(
        statusCode: 401,
        code: 'InvalidRefreshTokenError',
        message: 'invalid',
      ),
    );

    await expectLater(
      client.getJson('/me/profile'),
      throwsA(isA<ApiException>()),
    );
    expect(storage.access, isNull);
    expect(storage.refresh, isNull);
  });

  test('refreshes the token and retries the stream once after a 401', () async {
    final api = _MockApiClient();
    final storage = _InMemoryTokenStorage();
    final client = AuthenticatedApiClient(api, storage);

    // A stale access token is rejected before any SSE byte (this is how the
    // auth dependency rejects an expired token), so retrying the whole request
    // with a refreshed token is safe — no half-consumed stream to duplicate.
    when(
      () => api.postLineStream(
        '/sessions/1/turn/stream',
        body: any(named: 'body'),
        bearer: 'old-access',
      ),
    ).thenThrow(
      const ApiException(
        statusCode: 401,
        code: 'AuthenticationError',
        message: 'expired',
      ),
    );
    when(
      () =>
          api.postJson('/auth/refresh', body: {'refresh_token': 'old-refresh'}),
    ).thenAnswer(
      (_) async => {
        'access_token': 'new-access',
        'refresh_token': 'new-refresh',
      },
    );
    when(
      () => api.postLineStream(
        '/sessions/1/turn/stream',
        body: any(named: 'body'),
        bearer: 'new-access',
      ),
    ).thenAnswer(
      (_) => Stream.fromIterable(['event: done', 'data: {}', '']),
    );

    final lines = await client
        .postLineStream('/sessions/1/turn/stream', body: {'text': 'hi'})
        .toList();

    expect(lines, ['event: done', 'data: {}', '']);
    expect(storage.access, 'new-access');
    verify(
      () => api.postLineStream(
        '/sessions/1/turn/stream',
        body: any(named: 'body'),
        bearer: 'old-access',
      ),
    ).called(1);
    verify(
      () => api.postLineStream(
        '/sessions/1/turn/stream',
        body: any(named: 'body'),
        bearer: 'new-access',
      ),
    ).called(1);
  });

  test('propagates a non-401 stream error without refreshing', () async {
    final api = _MockApiClient();
    final storage = _InMemoryTokenStorage();
    final client = AuthenticatedApiClient(api, storage);

    when(
      () => api.postLineStream(
        any(),
        body: any(named: 'body'),
        bearer: any(named: 'bearer'),
      ),
    ).thenThrow(
      const ApiException(
        statusCode: 502,
        code: 'LlmProviderError',
        message: 'boom',
      ),
    );

    await expectLater(
      client
          .postLineStream('/sessions/1/turn/stream', body: {'text': 'hi'})
          .toList(),
      throwsA(isA<ApiException>()),
    );
    verifyNever(() => api.postJson('/auth/refresh', body: any(named: 'body')));
  });
}

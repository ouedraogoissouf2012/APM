import 'package:apm/src/core/network/api_client.dart';
import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/core/network/token_refresher.dart';
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
  // Every test below constructs its OWN TokenRefresher — sharing one across
  // test cases would leak generation/in-flight state between them.
  test(
    'refreshes tokens and retries once after an authenticated 401',
    () async {
      final api = _MockApiClient();
      final storage = _InMemoryTokenStorage();
      final client = AuthenticatedApiClient(
        api,
        storage,
        TokenRefresher(api, storage),
      );

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

  test(
    'clears tokens when the backend rejects the refresh token (401)',
    () async {
      final api = _MockApiClient();
      final storage = _InMemoryTokenStorage();
      final client = AuthenticatedApiClient(
        api,
        storage,
        TokenRefresher(api, storage),
      );

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
    },
  );

  test(
    '#315 — keeps tokens intact when the refresh call fails with a network error',
    () async {
      final api = _MockApiClient();
      final storage = _InMemoryTokenStorage();
      final client = AuthenticatedApiClient(
        api,
        storage,
        TokenRefresher(api, storage),
      );

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
      ).thenThrow(
        const ApiException(
          statusCode: 0,
          code: 'network',
          message: 'Network error',
        ),
      );

      await expectLater(
        client.getJson('/me/profile'),
        throwsA(isA<ApiException>()),
      );
      // The original 401 was real, but the offline blip that hit the refresh
      // call must not wipe tokens the learner may still be able to use once
      // connectivity returns.
      expect(storage.access, 'old-access');
      expect(storage.refresh, 'old-refresh');
    },
  );

  test('refreshes the token and retries the stream once after a 401', () async {
    final api = _MockApiClient();
    final storage = _InMemoryTokenStorage();
    final client = AuthenticatedApiClient(
      api,
      storage,
      TokenRefresher(api, storage),
    );

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
    ).thenAnswer((_) => Stream.fromIterable(['event: done', 'data: {}', '']));

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

  test(
    'collapses concurrent 401 refreshes into a single /auth/refresh (single-flight)',
    () async {
      final api = _MockApiClient();
      final storage = _InMemoryTokenStorage();
      final client = AuthenticatedApiClient(
        api,
        storage,
        TokenRefresher(api, storage),
      );

      // Two independent calls both hit a 401 on the same stale access token.
      when(() => api.getJson('/a', bearer: 'old-access')).thenThrow(
        const ApiException(
          statusCode: 401,
          code: 'AuthenticationError',
          message: 'expired',
        ),
      );
      when(() => api.getJson('/b', bearer: 'old-access')).thenThrow(
        const ApiException(
          statusCode: 401,
          code: 'AuthenticationError',
          message: 'expired',
        ),
      );

      // The refresh has a real await gap, so the second caller reaches the
      // refresh path while the first refresh is still in flight — the exact
      // race that used to rotate the single-use refresh token twice.
      var refreshCalls = 0;
      when(
        () => api.postJson(
          '/auth/refresh',
          body: {'refresh_token': 'old-refresh'},
        ),
      ).thenAnswer((_) async {
        refreshCalls++;
        await Future<void>.delayed(Duration.zero);
        return {'access_token': 'new-access', 'refresh_token': 'new-refresh'};
      });

      when(
        () => api.getJson('/a', bearer: 'new-access'),
      ).thenAnswer((_) async => {'ok': 'a'});
      when(
        () => api.getJson('/b', bearer: 'new-access'),
      ).thenAnswer((_) async => {'ok': 'b'});

      final results = await Future.wait([
        client.getJson('/a'),
        client.getJson('/b'),
      ]);

      expect(results[0]['ok'], 'a');
      expect(results[1]['ok'], 'b');
      // The crux: two 401s, but the refresh token is spent exactly once.
      expect(refreshCalls, 1);
      verify(
        () => api.postJson(
          '/auth/refresh',
          body: {'refresh_token': 'old-refresh'},
        ),
      ).called(1);
      expect(storage.access, 'new-access');
      expect(storage.refresh, 'new-refresh');
    },
  );

  test(
    'a refresh after the previous one settles rotates the new token, not the old',
    () async {
      final api = _MockApiClient();
      final storage = _InMemoryTokenStorage();
      final client = AuthenticatedApiClient(
        api,
        storage,
        TokenRefresher(api, storage),
      );

      when(() => api.getJson('/a', bearer: 'old-access')).thenThrow(
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
      when(
        () => api.getJson('/a', bearer: 'new-access'),
      ).thenAnswer((_) async => {'ok': 'a'});

      await client.getJson('/a');
      expect(storage.refresh, 'new-refresh');

      // A second, sequential 401 must read the freshly rotated refresh token —
      // the single-flight Future is cleared once the first refresh settles.
      when(() => api.getJson('/b', bearer: 'new-access')).thenThrow(
        const ApiException(
          statusCode: 401,
          code: 'AuthenticationError',
          message: 'expired',
        ),
      );
      when(
        () => api.postJson(
          '/auth/refresh',
          body: {'refresh_token': 'new-refresh'},
        ),
      ).thenAnswer(
        (_) async => {
          'access_token': 'newer-access',
          'refresh_token': 'newer-refresh',
        },
      );
      when(
        () => api.getJson('/b', bearer: 'newer-access'),
      ).thenAnswer((_) async => {'ok': 'b'});

      final json = await client.getJson('/b');
      expect(json['ok'], 'b');
      expect(storage.access, 'newer-access');
      expect(storage.refresh, 'newer-refresh');
    },
  );

  test('propagates a non-401 stream error without refreshing', () async {
    final api = _MockApiClient();
    final storage = _InMemoryTokenStorage();
    final client = AuthenticatedApiClient(
      api,
      storage,
      TokenRefresher(api, storage),
    );

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

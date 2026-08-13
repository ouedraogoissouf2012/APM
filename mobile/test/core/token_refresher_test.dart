import 'dart:async';

import 'package:apm/src/core/network/api_client.dart';
import 'package:apm/src/core/network/api_exception.dart';
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

const _tokenJson = {'access_token': 'new-access', 'refresh_token': 'new-ref'};

void main() {
  late _MockApiClient api;
  late _InMemoryTokenStorage storage;
  late TokenRefresher refresher;

  setUp(() {
    api = _MockApiClient();
    storage = _InMemoryTokenStorage();
    refresher = TokenRefresher(api, storage);
  });

  test(
    'refresh() persists the rotated tokens and returns the raw json',
    () async {
      when(
        () => api.postJson(
          '/auth/refresh',
          body: {'refresh_token': 'old-refresh'},
        ),
      ).thenAnswer((_) async => _tokenJson);

      final json = await refresher.refresh();

      expect(json, _tokenJson);
      expect(storage.access, 'new-access');
      expect(storage.refresh, 'new-ref');
    },
  );

  test(
    'throws without touching storage when there is no refresh token to send',
    () async {
      storage.refresh = null;
      await expectLater(refresher.refresh(), throwsA(isA<ApiException>()));
      verifyNever(
        () => api.postJson('/auth/refresh', body: any(named: 'body')),
      );
    },
  );

  group('#315 — clear tokens only on a definitive 401', () {
    test(
      'clears tokens when the backend rejects the refresh token (401)',
      () async {
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

        await expectLater(refresher.refresh(), throwsA(isA<ApiException>()));
        expect(storage.access, isNull);
        expect(storage.refresh, isNull);
      },
    );

    test(
      'keeps tokens intact when the refresh call fails with a network error',
      () async {
        // #315: ApiClient normalizes a connectivity failure (no HTTP response
        // at all — timeout, DNS failure, dropped connection) to statusCode 0,
        // code "network" (see ApiClient._toApiException). This must NOT be
        // treated as "the refresh token was rejected".
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

        await expectLater(refresher.refresh(), throwsA(isA<ApiException>()));
        // The tokens the learner already had must survive an offline blip —
        // an app that's offline-first cannot afford a phantom logout here.
        expect(storage.access, 'old-access');
        expect(storage.refresh, 'old-refresh');
      },
    );

    test(
      'keeps tokens intact on a non-401 server error (e.g. 500/502)',
      () async {
        when(
          () => api.postJson(
            '/auth/refresh',
            body: {'refresh_token': 'old-refresh'},
          ),
        ).thenThrow(
          const ApiException(
            statusCode: 502,
            code: 'LlmProviderError',
            message: 'upstream down',
          ),
        );

        await expectLater(refresher.refresh(), throwsA(isA<ApiException>()));
        expect(storage.access, 'old-access');
        expect(storage.refresh, 'old-refresh');
      },
    );
  });

  group('single-flight', () {
    test('collapses concurrent refreshes into a single POST', () async {
      var calls = 0;
      when(
        () => api.postJson(
          '/auth/refresh',
          body: {'refresh_token': 'old-refresh'},
        ),
      ).thenAnswer((_) async {
        calls++;
        await Future<void>.delayed(Duration.zero);
        return _tokenJson;
      });

      final results = await Future.wait([
        refresher.refresh(),
        refresher.refresh(),
      ]);

      expect(calls, 1);
      expect(results[0], _tokenJson);
      expect(results[1], _tokenJson);
    });

    test('a later, sequential refresh starts a fresh POST', () async {
      when(
        () => api.postJson(
          '/auth/refresh',
          body: {'refresh_token': 'old-refresh'},
        ),
      ).thenAnswer((_) async => _tokenJson);
      await refresher.refresh();
      expect(storage.refresh, 'new-ref');

      when(
        () => api.postJson('/auth/refresh', body: {'refresh_token': 'new-ref'}),
      ).thenAnswer(
        (_) async => {
          'access_token': 'newer-access',
          'refresh_token': 'newer-ref',
        },
      );
      await refresher.refresh();
      expect(storage.refresh, 'newer-ref');
    });
  });

  group('#316 — logout coordination', () {
    test(
      'a refresh already in flight when logout runs does not persist its result',
      () async {
        final serverResponded = Completer<void>();
        when(
          () => api.postJson(
            '/auth/refresh',
            body: {'refresh_token': 'old-refresh'},
          ),
        ).thenAnswer((_) async {
          await serverResponded.future;
          return _tokenJson;
        });

        final pending = refresher.refresh();

        // Simulate logout() running while the refresh above is still in
        // flight (its network call hasn't resolved yet).
        await refresher.invalidateAndClear();

        // NOW the server's (stale) response arrives.
        serverResponded.complete();
        await expectLater(pending, throwsA(isA<ApiException>()));

        // The late-arriving refresh must NOT have resurrected tokens on a
        // device the user just logged out of.
        expect(storage.access, isNull);
        expect(storage.refresh, isNull);
      },
    );

    test('a refresh started after a logout works normally once a later login '
        'restores a valid refresh token', () async {
      await refresher.invalidateAndClear();
      // A fresh login (out of TokenRefresher's scope — AuthRepository.login
      // saves it directly) restores a valid refresh token.
      storage.refresh = 'post-login-refresh';
      when(
        () => api.postJson(
          '/auth/refresh',
          body: {'refresh_token': 'post-login-refresh'},
        ),
      ).thenAnswer((_) async => _tokenJson);

      final json = await refresher.refresh();

      expect(json, _tokenJson);
      expect(storage.access, 'new-access');
    });

    test(
      'a refresh that starts reading its token WHILE invalidateAndClear() is '
      'still clearing storage still fails, never reaching the network',
      () async {
        // The residual race a bare "generation changed since I started" check
        // (compared only once, at save time) cannot close on its own: if this
        // refresh's token-read ran concurrently with clear() and happened to
        // observe the OLD, not-yet-wiped token plus the ALREADY-bumped
        // generation, a later "did generation change since MY start" check
        // would find no mismatch. Locking the read itself (see class doc)
        // forces it to land strictly before or after invalidateAndClear() —
        // this proves the "after" case: it must observe storage already
        // cleared, so it fails immediately without ever calling the backend.
        final clearStarted = Completer<void>();
        final releaseClear = Completer<void>();
        final gatedStorage = _ClearGatedTokenStorage(
          storage,
          onClearStarted: clearStarted,
          releaseClear: releaseClear.future,
        );
        final gatedRefresher = TokenRefresher(api, gatedStorage);

        final invalidation = gatedRefresher.invalidateAndClear();
        await clearStarted.future; // generation is bumped; clear() is in flight

        final pending = gatedRefresher.refresh();
        releaseClear.complete(); // let clear() (and invalidateAndClear) finish
        await invalidation;

        await expectLater(pending, throwsA(isA<ApiException>()));
        expect(storage.access, isNull);
        expect(storage.refresh, isNull);
        verifyNever(
          () => api.postJson('/auth/refresh', body: any(named: 'body')),
        );
      },
    );
  });
}

/// Wraps a [TokenStorage], letting a test hold `clear()` open at a precise
/// point — signals [onClearStarted] the instant it's called, then waits for
/// [releaseClear] before actually delegating. Every other method passes
/// straight through.
class _ClearGatedTokenStorage implements TokenStorage {
  _ClearGatedTokenStorage(
    this._inner, {
    required this.onClearStarted,
    required this.releaseClear,
  });

  final TokenStorage _inner;
  final Completer<void> onClearStarted;
  final Future<void> releaseClear;

  @override
  Future<void> save({
    required String accessToken,
    required String refreshToken,
  }) => _inner.save(accessToken: accessToken, refreshToken: refreshToken);

  @override
  Future<String?> readAccessToken() => _inner.readAccessToken();

  @override
  Future<String?> readRefreshToken() => _inner.readRefreshToken();

  @override
  Future<void> clear() async {
    onClearStarted.complete();
    await releaseClear;
    await _inner.clear();
  }
}

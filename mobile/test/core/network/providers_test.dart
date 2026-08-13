import 'dart:async';

import 'package:apm/src/core/network/api_client.dart';
import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/core/network/providers.dart';
import 'package:apm/src/core/storage/token_storage.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements ApiClient {}

class _InMemoryTokenStorage implements TokenStorage {
  String? access;
  String? refresh;

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
  test('tokenRefresherProvider is a singleton within a container', () {
    final container = ProviderContainer(
      overrides: [
        apiClientProvider.overrideWithValue(_MockApiClient()),
        tokenStorageProvider.overrideWithValue(_InMemoryTokenStorage()),
      ],
    );
    addTearDown(container.dispose);

    final first = container.read(tokenRefresherProvider);
    final second = container.read(tokenRefresherProvider);

    expect(identical(first, second), isTrue);
  });

  test(
    '#327 — authenticatedApiClientProvider and authRepositoryProvider share '
    'the SAME TokenRefresher, not two independent ones',
    () async {
      // Reproduces the exact #316 scenario end-to-end through the REAL
      // provider graph (not a hand-wired TokenRefresher passed to both
      // constructors, which test/data/auth_repository_test.dart already
      // covers at the class level) — this is what actually proves the
      // providers wire up sharing correctly, since a regression here (e.g.
      // each provider building its own `TokenRefresher(...)` again) would
      // NOT be caught by that lower-level test. If AuthenticatedApiClient's
      // 401-triggered refresh and AuthRepository.logout() ran against two
      // DIFFERENT TokenRefresher instances, logout()'s invalidateAndClear()
      // would never see (or block) the in-flight refresh below, and the
      // stale response would resurrect the session logout() just ended.
      final api = _MockApiClient();
      final storage = _InMemoryTokenStorage()
        ..access = 'old-access'
        ..refresh = 'old-refresh';
      final container = ProviderContainer(
        overrides: [
          apiClientProvider.overrideWithValue(api),
          tokenStorageProvider.overrideWithValue(storage),
        ],
      );
      addTearDown(container.dispose);

      final client = container.read(authenticatedApiClientProvider);
      final repo = container.read(authRepositoryProvider);

      when(() => api.getJson('/me/profile', bearer: 'old-access')).thenThrow(
        const ApiException(
          statusCode: 401,
          code: 'AuthenticationError',
          message: 'expired',
        ),
      );
      final refreshStarted = Completer<void>();
      final serverResponded = Completer<void>();
      when(
        () => api.postJson(
          '/auth/refresh',
          body: {'refresh_token': 'old-refresh'},
        ),
      ).thenAnswer((_) async {
        refreshStarted.complete();
        await serverResponded.future;
        return {'access_token': 'new-access', 'refresh_token': 'new-refresh'};
      });
      when(
        () => api.postJson(
          '/auth/logout',
          body: {'refresh_token': 'old-refresh'},
        ),
      ).thenAnswer((_) async => {});

      final pendingRequest = client.getJson('/me/profile');
      await refreshStarted.future; // the 401-triggered refresh is now in flight

      await repo.logout(); // runs on the OTHER provider's repository

      serverResponded.complete(); // the stale refresh response finally arrives

      // The original request must fail — not silently succeed with a token
      // that was never persisted, because logout() already invalidated the
      // in-flight refresh through the TokenRefresher THEY BOTH SHARE.
      await expectLater(pendingRequest, throwsA(isA<ApiException>()));
      expect(storage.access, isNull);
      expect(storage.refresh, isNull);
    },
  );
}

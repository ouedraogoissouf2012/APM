import 'dart:async';

import 'package:apm/src/core/network/api_client.dart';
import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/core/network/token_refresher.dart';
import 'package:apm/src/core/storage/token_storage.dart';
import 'package:apm/src/data/repositories/auth_repository.dart';
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
  late _MockApiClient api;
  late _InMemoryTokenStorage storage;
  late TokenRefresher refresher;
  late AuthRepository repo;

  setUp(() {
    api = _MockApiClient();
    storage = _InMemoryTokenStorage();
    // A fresh TokenRefresher per test — sharing one across test cases would
    // leak generation/in-flight state between them.
    refresher = TokenRefresher(api, storage);
    repo = AuthRepository(api, storage, refresher);
  });

  const tokenResponse = {
    'access_token': 'acc',
    'refresh_token': 'ref',
    'token_type': 'bearer',
    'user': {
      'id': 1,
      'email': 'a@b.com',
      'native_language': 'fr',
      'cefr_level': 'A1',
      'tier': 'free',
    },
  };

  test('register stores tokens and returns the user', () async {
    when(
      () => api.postJson('/auth/register', body: any(named: 'body')),
    ).thenAnswer((_) async => tokenResponse);

    final user = await repo.register(email: 'a@b.com', password: 's3cret!');

    expect(user.email, 'a@b.com');
    expect(storage.access, 'acc');
    expect(storage.refresh, 'ref');
  });

  test('login stores tokens and returns the user', () async {
    when(
      () => api.postJson('/auth/login', body: any(named: 'body')),
    ).thenAnswer((_) async => tokenResponse);

    final user = await repo.login(email: 'a@b.com', password: 's3cret!');

    expect(user.cefrLevel, 'A1');
    expect(storage.access, 'acc');
  });

  test('currentUser returns null when no token stored', () async {
    expect(await repo.currentUser(), isNull);
  });

  test('currentUser fetches /auth/me when a token is stored', () async {
    storage.access = 'acc';
    when(() => api.getJson('/auth/me', bearer: 'acc')).thenAnswer(
      (_) async => {
        'id': 1,
        'email': 'a@b.com',
        'native_language': 'fr',
        'cefr_level': 'B1',
        'tier': 'free',
      },
    );

    final user = await repo.currentUser();
    expect(user, isNotNull);
    expect(user!.cefrLevel, 'B1');
  });

  test('refresh stores rotated tokens and returns the user', () async {
    storage.refresh = 'old-refresh';
    when(
      () =>
          api.postJson('/auth/refresh', body: {'refresh_token': 'old-refresh'}),
    ).thenAnswer(
      (_) async => {
        'access_token': 'new-acc',
        'refresh_token': 'new-ref',
        'token_type': 'bearer',
        'user': {
          'id': 1,
          'email': 'a@b.com',
          'native_language': 'fr',
          'cefr_level': 'A2',
          'tier': 'free',
        },
      },
    );

    final user = await repo.refresh();

    expect(user.cefrLevel, 'A2');
    expect(storage.access, 'new-acc');
    expect(storage.refresh, 'new-ref');
  });

  test(
    'refresh clears tokens when the backend rejects the refresh token',
    () async {
      storage.access = 'old-acc';
      storage.refresh = 'old-refresh';
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

      await expectLater(repo.refresh(), throwsA(isA<ApiException>()));
      expect(storage.access, isNull);
      expect(storage.refresh, isNull);
    },
  );

  test('logout clears stored tokens', () async {
    storage.access = 'acc';
    storage.refresh = 'ref';
    when(
      () => api.postJson('/auth/logout', body: any(named: 'body')),
    ).thenAnswer((_) async => {});

    await repo.logout();
    expect(storage.access, isNull);
    expect(storage.refresh, isNull);
  });

  test('logout clears stored tokens even when backend logout fails', () async {
    storage.access = 'acc';
    storage.refresh = 'ref';
    when(
      () => api.postJson('/auth/logout', body: any(named: 'body')),
    ).thenThrow(
      const ApiException(
        statusCode: 500,
        code: 'ServerError',
        message: 'temporary failure',
      ),
    );

    await expectLater(repo.logout(), throwsA(isA<ApiException>()));
    expect(storage.access, isNull);
    expect(storage.refresh, isNull);
  });

  test(
    '#315 — refresh keeps tokens intact when the backend is merely unreachable',
    () async {
      storage.access = 'old-acc';
      storage.refresh = 'old-refresh';
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

      await expectLater(repo.refresh(), throwsA(isA<ApiException>()));
      // A network hiccup must not wipe still-valid tokens — an offline-first
      // app cannot afford a phantom logout on a dropped connection.
      expect(storage.access, 'old-acc');
      expect(storage.refresh, 'old-refresh');
    },
  );

  test('#316 — a refresh in flight via AuthenticatedApiClient is discarded if '
      'logout() runs before it resolves', () async {
    // The exact scenario #316 describes: a refresh started via the OTHER
    // class (AuthenticatedApiClient, on a 401) is still in flight when
    // logout() runs on THIS repository — they must coordinate through the
    // TokenRefresher they share, or the late response resurrects the
    // session logout() just ended.
    storage.access = 'old-access';
    storage.refresh = 'old-refresh';
    final authClient = AuthenticatedApiClient(api, storage, refresher);

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
      () =>
          api.postJson('/auth/refresh', body: {'refresh_token': 'old-refresh'}),
    ).thenAnswer((_) async {
      refreshStarted.complete();
      await serverResponded.future;
      return {'access_token': 'new-access', 'refresh_token': 'new-refresh'};
    });
    when(
      () =>
          api.postJson('/auth/logout', body: {'refresh_token': 'old-refresh'}),
    ).thenAnswer((_) async => {});

    final pendingRequest = authClient.getJson('/me/profile');
    await refreshStarted.future; // the refresh is now genuinely in flight

    await repo.logout(); // runs while that refresh is still pending

    serverResponded.complete(); // the stale response finally arrives

    // The original request must fail — not silently succeed with a token
    // that was never persisted (the user just logged out).
    await expectLater(pendingRequest, throwsA(isA<ApiException>()));
    expect(storage.access, isNull);
    expect(storage.refresh, isNull);
  });

  test('requestPasswordReset posts /auth/forgot-password', () async {
    when(
      () => api.postJson('/auth/forgot-password', body: any(named: 'body')),
    ).thenAnswer((_) async => {'status': 'ok'});

    await repo.requestPasswordReset(email: 'a@b.com');

    verify(
      () => api.postJson('/auth/forgot-password', body: {'email': 'a@b.com'}),
    ).called(1);
  });

  test('resetPassword posts /auth/reset-password', () async {
    when(
      () => api.postJson('/auth/reset-password', body: any(named: 'body')),
    ).thenAnswer((_) async => {});

    await repo.resetPassword(token: 'tok', newPassword: 'n3w!password');

    verify(
      () => api.postJson(
        '/auth/reset-password',
        body: {'token': 'tok', 'new_password': 'n3w!password'},
      ),
    ).called(1);
  });
}

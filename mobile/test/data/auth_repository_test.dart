import 'package:apm/src/core/network/api_client.dart';
import 'package:apm/src/core/storage/token_storage.dart';
import 'package:apm/src/data/repositories/auth_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements ApiClient {}

class _InMemoryTokenStorage implements TokenStorage {
  String? access;
  String? refresh;
  @override
  Future<void> save({required String accessToken, required String refreshToken}) async {
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
  late AuthRepository repo;

  setUp(() {
    api = _MockApiClient();
    storage = _InMemoryTokenStorage();
    repo = AuthRepository(api, storage);
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
    when(() => api.postJson('/auth/register', body: any(named: 'body')))
        .thenAnswer((_) async => tokenResponse);

    final user = await repo.register(email: 'a@b.com', password: 's3cret!');

    expect(user.email, 'a@b.com');
    expect(storage.access, 'acc');
    expect(storage.refresh, 'ref');
  });

  test('login stores tokens and returns the user', () async {
    when(() => api.postJson('/auth/login', body: any(named: 'body')))
        .thenAnswer((_) async => tokenResponse);

    final user = await repo.login(email: 'a@b.com', password: 's3cret!');

    expect(user.cefrLevel, 'A1');
    expect(storage.access, 'acc');
  });

  test('currentUser returns null when no token stored', () async {
    expect(await repo.currentUser(), isNull);
  });

  test('currentUser fetches /auth/me when a token is stored', () async {
    storage.access = 'acc';
    when(() => api.getJson('/auth/me', bearer: 'acc')).thenAnswer((_) async => {
          'id': 1,
          'email': 'a@b.com',
          'native_language': 'fr',
          'cefr_level': 'B1',
          'tier': 'free',
        });

    final user = await repo.currentUser();
    expect(user, isNotNull);
    expect(user!.cefrLevel, 'B1');
  });

  test('logout clears stored tokens', () async {
    storage.access = 'acc';
    storage.refresh = 'ref';
    when(() => api.postJson('/auth/logout', body: any(named: 'body')))
        .thenAnswer((_) async => {});

    await repo.logout();
    expect(storage.access, isNull);
    expect(storage.refresh, isNull);
  });
}

# App Flutter — Fondation + tranche Auth (sous-projet 6, PR 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the Flutter mobile app with the official MVVM + Riverpod architecture and deliver a complete, tested **auth vertical slice** (register / login / logout / "stay logged in") wired to the existing FastAPI backend.

**Architecture:** Official Flutter app architecture (MVVM + Repository), "Compass-hybrid" layout: `ui/` grouped by feature (each screen = a View + a ViewModel), `data/` grouped by type (`models/`, `repositories/`, services). State management & DI: **Riverpod 3 with codegen** (`@riverpod`). Models: **freezed** + json_serializable. Routing: **go_router** with an auth redirect. Networking: **Dio**. Tokens stored in **flutter_secure_storage**. ViewModels hold no widgets; Views hold no business logic; Repositories are the single source of truth and the only thing that talks to the API client.

**Tech Stack:** Flutter 3.38 / Dart 3, flutter_riverpod + riverpod_annotation + riverpod_generator, freezed + json_serializable, go_router, dio, flutter_secure_storage, build_runner; tests with flutter_test + mocktail.

---

## Prerequisites & conventions

- Flutter 3.38.5 is installed (`C:\flutter\bin\flutter.bat`). Devices available: Windows desktop, Chrome, Edge. Use **Chrome** for quick visual runs (`flutter run -d chrome`) and `flutter test` for tests.
- The Flutter app lives in a NEW top-level folder: `mobile/` (sibling of `backend/`).
- All commands below run from `mobile/` unless noted: `Set-Location "c:\Users\USER PC\Documents\propre à moi\anglais pour moi\mobile"`.
- After codegen changes run `dart run build_runner build --delete-conflicting-outputs`.
- Quality gates for the Flutter app (run at the end of each task; must pass): `flutter analyze` and `flutter test`.
- The backend exposes (already built): `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`. Register/login return `{access_token, refresh_token, token_type, user:{id,email,native_language,cefr_level,tier}}`. CORS is enabled on the backend.
- Git identity for commits: `git -c user.name="ouedraogoissouf2012" -c user.email="adcdevteam2025@gmail.com" commit -m "<msg>"` ending with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure (this PR)

```
mobile/
  pubspec.yaml
  analysis_options.yaml
  lib/
    main.dart
    src/
      core/
        config/app_config.dart
        network/api_client.dart
        network/api_exception.dart
        storage/token_storage.dart
        router/app_router.dart
      data/
        models/auth_tokens.dart
        models/app_user.dart
        repositories/auth_repository.dart
      ui/
        auth/
          view_model/auth_view_model.dart
          widgets/login_screen.dart
          widgets/register_screen.dart
        home/
          widgets/home_screen.dart
  test/
    data/auth_repository_test.dart
    ui/auth_view_model_test.dart
    ui/login_screen_test.dart
.github/workflows/ci.yml   # add a Flutter job
```

---

### Task 1: Scaffold the Flutter project + dependencies

**Files:** create the `mobile/` Flutter project; edit `mobile/pubspec.yaml`, `mobile/analysis_options.yaml`.

- [ ] **Step 1: Create the project** (from repo root `c:\Users\USER PC\Documents\propre à moi\anglais pour moi`):
```bash
flutter create --org com.apm --project-name apm mobile
```
Expected: a new `mobile/` folder with a runnable Flutter app.

- [ ] **Step 2: Add dependencies via `flutter pub add`** (resolves the latest compatible versions automatically — this pulls **Riverpod 3.x**, whose codegen uses the generic `Ref` parameter the rest of this plan relies on). From `mobile/`:
```bash
flutter pub add flutter_riverpod riverpod_annotation go_router dio freezed_annotation json_annotation flutter_secure_storage
flutter pub add dev:build_runner dev:riverpod_generator dev:freezed dev:json_serializable dev:riverpod_lint dev:custom_lint dev:mocktail
```
Expected: pubspec.yaml is updated and dependencies resolve without error. Confirm `flutter_riverpod` resolves to a **3.x** version (`flutter pub deps | Select-String riverpod`); if your environment only has Riverpod 2.x available, STOP and report (the codegen `Ref` signatures in later tasks assume Riverpod 3).

- [ ] **Step 3: Confirm install**:
```bash
flutter pub get
```
Expected: resolves without error.

- [ ] **Step 4: Set `mobile/analysis_options.yaml`** to:
```yaml
include: package:flutter_lints/flutter.yaml

analyzer:
  plugins:
    - custom_lint
  errors:
    invalid_annotation_target: ignore

linter:
  rules:
    prefer_const_constructors: true
```

- [ ] **Step 5: Verify it builds/tests** (the default template test exists):
```bash
flutter analyze
flutter test
```
Expected: analyze passes (warnings ok), default widget test passes. If the default `test/widget_test.dart` references the removed counter app, delete it: `Remove-Item test/widget_test.dart` (we add our own tests later).

- [ ] **Step 6: Commit** (from repo root):
```bash
git add mobile/pubspec.yaml mobile/analysis_options.yaml mobile/lib mobile/test mobile/android mobile/ios mobile/web mobile/pubspec.lock mobile/.gitignore mobile/.metadata
git -c user.name="ouedraogoissouf2012" -c user.email="adcdevteam2025@gmail.com" commit -m "chore(mobile): scaffold Flutter app + deps (riverpod, freezed, go_router, dio)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Config + Dio API client + typed API exception

**Files:** create `mobile/lib/src/core/config/app_config.dart`, `mobile/lib/src/core/network/api_exception.dart`, `mobile/lib/src/core/network/api_client.dart`.

- [ ] **Step 1: Create `app_config.dart`**
```dart
class AppConfig {
  const AppConfig({required this.apiBaseUrl});

  /// On web/desktop dev the backend runs at localhost:8000. Android emulators
  /// reach the host machine via 10.0.2.2.
  final String apiBaseUrl;

  static const AppConfig dev = AppConfig(apiBaseUrl: 'http://localhost:8000');
}
```

- [ ] **Step 2: Create `api_exception.dart`**
```dart
/// A normalized API error. The backend returns `{ "error": { "code", "message" } }`.
class ApiException implements Exception {
  const ApiException({required this.statusCode, required this.code, required this.message});

  final int statusCode;
  final String code;
  final String message;

  @override
  String toString() => 'ApiException($statusCode, $code): $message';
}
```

- [ ] **Step 3: Create `api_client.dart`** (thin Dio wrapper that maps backend errors to `ApiException`)
```dart
import 'package:dio/dio.dart';

import '../config/app_config.dart';
import 'api_exception.dart';

class ApiClient {
  ApiClient(AppConfig config, {Dio? dio})
      : _dio = dio ?? Dio(BaseOptions(baseUrl: config.apiBaseUrl));

  final Dio _dio;

  Dio get raw => _dio;

  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    String? bearer,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        path,
        data: body,
        options: _options(bearer),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  Future<Map<String, dynamic>> getJson(String path, {String? bearer}) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(path, options: _options(bearer));
      return response.data ?? <String, dynamic>{};
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  Options _options(String? bearer) => Options(
        headers: bearer == null ? null : {'Authorization': 'Bearer $bearer'},
      );

  ApiException _toApiException(DioException e) {
    final status = e.response?.statusCode ?? 0;
    final data = e.response?.data;
    if (data is Map && data['error'] is Map) {
      final err = data['error'] as Map;
      return ApiException(
        statusCode: status,
        code: (err['code'] ?? 'error').toString(),
        message: (err['message'] ?? 'Request failed').toString(),
      );
    }
    return ApiException(statusCode: status, code: 'network', message: e.message ?? 'Network error');
  }
}
```

- [ ] **Step 4: Verify**: `flutter analyze` (these files have no tests yet; they are exercised in Task 4).
Expected: no analyzer errors.

- [ ] **Step 5: Commit**
```bash
git add mobile/lib/src/core
git -c user.name="ouedraogoissouf2012" -c user.email="adcdevteam2025@gmail.com" commit -m "feat(mobile): app config + Dio API client + ApiException

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Domain models (freezed) — AppUser + AuthTokens

**Files:** create `mobile/lib/src/data/models/app_user.dart`, `mobile/lib/src/data/models/auth_tokens.dart`; generate `.freezed.dart`/`.g.dart`.

- [ ] **Step 1: Create `app_user.dart`**
```dart
import 'package:freezed_annotation/freezed_annotation.dart';

part 'app_user.freezed.dart';
part 'app_user.g.dart';

@freezed
class AppUser with _$AppUser {
  const factory AppUser({
    required int id,
    required String email,
    @JsonKey(name: 'native_language') required String nativeLanguage,
    @JsonKey(name: 'cefr_level') required String cefrLevel,
    required String tier,
  }) = _AppUser;

  factory AppUser.fromJson(Map<String, dynamic> json) => _$AppUserFromJson(json);
}
```

- [ ] **Step 2: Create `auth_tokens.dart`**
```dart
import 'package:freezed_annotation/freezed_annotation.dart';

part 'auth_tokens.freezed.dart';
part 'auth_tokens.g.dart';

@freezed
class AuthTokens with _$AuthTokens {
  const factory AuthTokens({
    @JsonKey(name: 'access_token') required String accessToken,
    @JsonKey(name: 'refresh_token') required String refreshToken,
  }) = _AuthTokens;

  factory AuthTokens.fromJson(Map<String, dynamic> json) => _$AuthTokensFromJson(json);
}
```

- [ ] **Step 3: Run codegen**
```bash
dart run build_runner build --delete-conflicting-outputs
```
Expected: generates `app_user.freezed.dart`, `app_user.g.dart`, `auth_tokens.freezed.dart`, `auth_tokens.g.dart`.

- [ ] **Step 4: Verify**: `flutter analyze`. Expected: no errors.

- [ ] **Step 5: Commit**
```bash
git add mobile/lib/src/data/models
git -c user.name="ouedraogoissouf2012" -c user.email="adcdevteam2025@gmail.com" commit -m "feat(mobile): AppUser + AuthTokens freezed models

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: TokenStorage + AuthRepository (TDD)

**Files:** create `mobile/lib/src/core/storage/token_storage.dart`, `mobile/lib/src/data/repositories/auth_repository.dart`; test `mobile/test/data/auth_repository_test.dart`.

- [ ] **Step 1: Create `token_storage.dart`** (abstraction over secure storage so it's fakeable in tests)
```dart
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract class TokenStorage {
  Future<void> save({required String accessToken, required String refreshToken});
  Future<String?> readAccessToken();
  Future<String?> readRefreshToken();
  Future<void> clear();
}

class SecureTokenStorage implements TokenStorage {
  SecureTokenStorage([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;
  static const _access = 'access_token';
  static const _refresh = 'refresh_token';

  @override
  Future<void> save({required String accessToken, required String refreshToken}) async {
    await _storage.write(key: _access, value: accessToken);
    await _storage.write(key: _refresh, value: refreshToken);
  }

  @override
  Future<String?> readAccessToken() => _storage.read(key: _access);

  @override
  Future<String?> readRefreshToken() => _storage.read(key: _refresh);

  @override
  Future<void> clear() async {
    await _storage.delete(key: _access);
    await _storage.delete(key: _refresh);
  }
}
```

- [ ] **Step 2: Write the failing test — `mobile/test/data/auth_repository_test.dart`**
```dart
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
```

- [ ] **Step 3: Run — verify it fails** (`flutter test test/data/auth_repository_test.dart`): `AuthRepository` not defined.

- [ ] **Step 4: Create `auth_repository.dart`**
```dart
import '../../core/network/api_client.dart';
import '../../core/storage/token_storage.dart';
import '../models/app_user.dart';
import '../models/auth_tokens.dart';

class AuthRepository {
  AuthRepository(this._api, this._storage);

  final ApiClient _api;
  final TokenStorage _storage;

  Future<AppUser> register({
    required String email,
    required String password,
    String nativeLanguage = 'fr',
  }) async {
    final json = await _api.postJson('/auth/register', body: {
      'email': email,
      'password': password,
      'native_language': nativeLanguage,
    });
    return _persistAndExtractUser(json);
  }

  Future<AppUser> login({required String email, required String password}) async {
    final json = await _api.postJson('/auth/login', body: {
      'email': email,
      'password': password,
    });
    return _persistAndExtractUser(json);
  }

  Future<AppUser?> currentUser() async {
    final token = await _storage.readAccessToken();
    if (token == null) return null;
    final json = await _api.getJson('/auth/me', bearer: token);
    return AppUser.fromJson(json);
  }

  Future<void> logout() async {
    final refresh = await _storage.readRefreshToken();
    if (refresh != null) {
      await _api.postJson('/auth/logout', body: {'refresh_token': refresh});
    }
    await _storage.clear();
  }

  Future<AppUser> _persistAndExtractUser(Map<String, dynamic> json) async {
    final tokens = AuthTokens.fromJson(json);
    await _storage.save(accessToken: tokens.accessToken, refreshToken: tokens.refreshToken);
    return AppUser.fromJson(json['user'] as Map<String, dynamic>);
  }
}
```

- [ ] **Step 5: Run — verify 5 passed** (`flutter test test/data/auth_repository_test.dart`).

- [ ] **Step 6: `flutter analyze`** — no errors. Commit:
```bash
git add mobile/lib/src/core/storage mobile/lib/src/data/repositories mobile/test/data
git -c user.name="ouedraogoissouf2012" -c user.email="adcdevteam2025@gmail.com" commit -m "feat(mobile): TokenStorage + AuthRepository (tested)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Auth providers + AuthViewModel (Riverpod codegen) (TDD)

**Files:** create `mobile/lib/src/ui/auth/view_model/auth_view_model.dart`; test `mobile/test/ui/auth_view_model_test.dart`; generate `.g.dart`.

- [ ] **Step 1: Create `auth_view_model.dart`** (providers + an AsyncNotifier holding the auth state)
```dart
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/config/app_config.dart';
import '../../../core/network/api_client.dart';
import '../../../core/storage/token_storage.dart';
import '../../../data/models/app_user.dart';
import '../../../data/repositories/auth_repository.dart';

part 'auth_view_model.g.dart';

@riverpod
ApiClient apiClient(Ref ref) => ApiClient(AppConfig.dev);

@riverpod
TokenStorage tokenStorage(Ref ref) => SecureTokenStorage();

@riverpod
AuthRepository authRepository(Ref ref) =>
    AuthRepository(ref.watch(apiClientProvider), ref.watch(tokenStorageProvider));

/// Holds the current authenticated user (null = signed out). Loads on startup.
@riverpod
class AuthViewModel extends _$AuthViewModel {
  @override
  Future<AppUser?> build() => ref.watch(authRepositoryProvider).currentUser();

  Future<void> login({required String email, required String password}) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref.read(authRepositoryProvider).login(email: email, password: password),
    );
  }

  Future<void> register({
    required String email,
    required String password,
    String nativeLanguage = 'fr',
  }) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref
          .read(authRepositoryProvider)
          .register(email: email, password: password, nativeLanguage: nativeLanguage),
    );
  }

  Future<void> logout() async {
    await ref.read(authRepositoryProvider).logout();
    state = const AsyncData(null);
  }
}
```

- [ ] **Step 2: Run codegen**:
```bash
dart run build_runner build --delete-conflicting-outputs
```
Expected: generates `auth_view_model.g.dart`.

- [ ] **Step 3: Write the test — `mobile/test/ui/auth_view_model_test.dart`** (override the repository provider with a fake)
```dart
import 'package:apm/src/data/models/app_user.dart';
import 'package:apm/src/data/repositories/auth_repository.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuthRepository extends Mock implements AuthRepository {}

const _user = AppUser(
  id: 1,
  email: 'a@b.com',
  nativeLanguage: 'fr',
  cefrLevel: 'A1',
  tier: 'free',
);

ProviderContainer _containerWith(AuthRepository repo) {
  final c = ProviderContainer(
    overrides: [authRepositoryProvider.overrideWithValue(repo)],
  );
  addTearDown(c.dispose);
  return c;
}

void main() {
  test('build returns null when signed out', () async {
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => null);
    final c = _containerWith(repo);

    final user = await c.read(authViewModelProvider.future);
    expect(user, isNull);
  });

  test('login sets the authenticated user', () async {
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => null);
    when(() => repo.login(email: any(named: 'email'), password: any(named: 'password')))
        .thenAnswer((_) async => _user);
    final c = _containerWith(repo);

    await c.read(authViewModelProvider.future); // initial build
    await c.read(authViewModelProvider.notifier).login(email: 'a@b.com', password: 's3cret!');

    expect(c.read(authViewModelProvider).value, _user);
  });

  test('logout clears the user', () async {
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => _user);
    when(repo.logout).thenAnswer((_) async {});
    final c = _containerWith(repo);

    await c.read(authViewModelProvider.future);
    await c.read(authViewModelProvider.notifier).logout();

    expect(c.read(authViewModelProvider).value, isNull);
  });
}
```

- [ ] **Step 4: Run — verify 3 passed** (`flutter test test/ui/auth_view_model_test.dart`).

- [ ] **Step 5: `flutter analyze`** — no errors. Commit:
```bash
git add mobile/lib/src/ui/auth/view_model mobile/test/ui/auth_view_model_test.dart
git -c user.name="ouedraogoissouf2012" -c user.email="adcdevteam2025@gmail.com" commit -m "feat(mobile): auth providers + AuthViewModel (Riverpod codegen, tested)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Login & Register screens + Home placeholder (TDD widget test)

**Files:** create `mobile/lib/src/ui/auth/widgets/login_screen.dart`, `register_screen.dart`, `mobile/lib/src/ui/home/widgets/home_screen.dart`; test `mobile/test/ui/login_screen_test.dart`.

- [ ] **Step 1: Create `home_screen.dart`**
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../auth/view_model/auth_view_model.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authViewModelProvider).value;
    return Scaffold(
      appBar: AppBar(
        title: const Text('APM'),
        actions: [
          IconButton(
            key: const Key('logout_button'),
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(authViewModelProvider.notifier).logout(),
          ),
        ],
      ),
      body: Center(
        child: Text(
          user == null ? 'Welcome' : 'Hello, ${user.email} (${user.cefrLevel})',
        ),
      ),
    );
  }
}
```

- [ ] **Step 2: Create `login_screen.dart`**
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../view_model/auth_view_model.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authViewModelProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Log in')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TextField(
              key: const Key('email_field'),
              controller: _email,
              decoration: const InputDecoration(labelText: 'Email'),
            ),
            TextField(
              key: const Key('password_field'),
              controller: _password,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Password'),
            ),
            const SizedBox(height: 16),
            if (auth.hasError)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  'Login failed',
                  key: const Key('login_error'),
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            FilledButton(
              key: const Key('login_button'),
              onPressed: auth.isLoading
                  ? null
                  : () => ref.read(authViewModelProvider.notifier).login(
                        email: _email.text,
                        password: _password.text,
                      ),
              child: auth.isLoading
                  ? const CircularProgressIndicator()
                  : const Text('Log in'),
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 3: Create `register_screen.dart`** (same shape as login, calling `register`)
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../view_model/auth_view_model.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authViewModelProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Create account')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TextField(
              key: const Key('email_field'),
              controller: _email,
              decoration: const InputDecoration(labelText: 'Email'),
            ),
            TextField(
              key: const Key('password_field'),
              controller: _password,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Password'),
            ),
            const SizedBox(height: 16),
            FilledButton(
              key: const Key('register_button'),
              onPressed: auth.isLoading
                  ? null
                  : () => ref.read(authViewModelProvider.notifier).register(
                        email: _email.text,
                        password: _password.text,
                      ),
              child: const Text('Create account'),
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Write the widget test — `mobile/test/ui/login_screen_test.dart`**
```dart
import 'package:apm/src/data/models/app_user.dart';
import 'package:apm/src/data/repositories/auth_repository.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:apm/src/ui/auth/widgets/login_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuthRepository extends Mock implements AuthRepository {}

void main() {
  testWidgets('entering credentials and tapping log in calls the repository', (tester) async {
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => null);
    when(() => repo.login(email: any(named: 'email'), password: any(named: 'password')))
        .thenAnswer((_) async => const AppUser(
              id: 1,
              email: 'a@b.com',
              nativeLanguage: 'fr',
              cefrLevel: 'A1',
              tier: 'free',
            ));

    await tester.pumpWidget(
      ProviderScope(
        overrides: [authRepositoryProvider.overrideWithValue(repo)],
        child: const MaterialApp(home: LoginScreen()),
      ),
    );
    await tester.pump(); // resolve initial build

    await tester.enterText(find.byKey(const Key('email_field')), 'a@b.com');
    await tester.enterText(find.byKey(const Key('password_field')), 's3cret!');
    await tester.tap(find.byKey(const Key('login_button')));
    await tester.pump();

    verify(() => repo.login(email: 'a@b.com', password: 's3cret!')).called(1);
  });
}
```

- [ ] **Step 5: Run — verify it passes** (`flutter test test/ui/login_screen_test.dart`).

- [ ] **Step 6: `flutter analyze`** — no errors. Commit:
```bash
git add mobile/lib/src/ui/auth/widgets mobile/lib/src/ui/home mobile/test/ui/login_screen_test.dart
git -c user.name="ouedraogoissouf2012" -c user.email="adcdevteam2025@gmail.com" commit -m "feat(mobile): login/register screens + home placeholder (widget-tested)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Router (go_router auth redirect) + wire main.dart

**Files:** create `mobile/lib/src/core/router/app_router.dart`; replace `mobile/lib/main.dart`.

- [ ] **Step 1: Create `app_router.dart`** (redirects to /login when signed out, to /home when signed in)
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../ui/auth/view_model/auth_view_model.dart';
import '../../ui/auth/widgets/login_screen.dart';
import '../../ui/auth/widgets/register_screen.dart';
import '../../ui/home/widgets/home_screen.dart';

part 'app_router.g.dart';

@riverpod
GoRouter appRouter(Ref ref) {
  return GoRouter(
    initialLocation: '/login',
    redirect: (context, state) {
      final auth = ref.read(authViewModelProvider);
      final signedIn = auth.value != null;
      final atAuth = state.matchedLocation == '/login' || state.matchedLocation == '/register';
      if (auth.isLoading) return null;
      if (!signedIn && !atAuth) return '/login';
      if (signedIn && atAuth) return '/home';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      GoRoute(path: '/register', builder: (_, __) => const RegisterScreen()),
      GoRoute(path: '/home', builder: (_, __) => const HomeScreen()),
    ],
  );
}
```

- [ ] **Step 2: Run codegen**: `dart run build_runner build --delete-conflicting-outputs` (generates `app_router.g.dart`).

- [ ] **Step 3: Replace `mobile/lib/main.dart`**
```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'src/core/router/app_router.dart';

void main() {
  runApp(const ProviderScope(child: ApmApp()));
}

class ApmApp extends ConsumerWidget {
  const ApmApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);
    return MaterialApp.router(
      title: 'APM',
      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
      routerConfig: router,
    );
  }
}
```

- [ ] **Step 4: Verify**: `flutter analyze` (no errors) and `flutter test` (all prior tests still pass). Optionally run visually: `flutter run -d chrome` (requires the backend at localhost:8000 to actually log in, but the app boots to the login screen regardless).

- [ ] **Step 5: Commit**
```bash
git add mobile/lib/src/core/router mobile/lib/main.dart
git -c user.name="ouedraogoissouf2012" -c user.email="adcdevteam2025@gmail.com" commit -m "feat(mobile): go_router auth redirect + app entrypoint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Flutter CI job + .gitignore for generated files

**Files:** modify `.github/workflows/ci.yml`; ensure `mobile/.gitignore` ignores generated files.

- [ ] **Step 1: Confirm `mobile/.gitignore` ignores build artifacts but COMMITS generated `.g.dart`/`.freezed.dart`.**
Decision: we COMMIT generated files (simpler CI, no codegen step needed to analyze/test). Ensure `.gitignore` does NOT list `*.g.dart` or `*.freezed.dart` (the default Flutter `.gitignore` does not). If present, remove those lines.

- [ ] **Step 2: Add a Flutter job to `.github/workflows/ci.yml`** (append after the existing `backend:` job, at the same indentation level under `jobs:`):
```yaml
  mobile:
    name: Mobile (analyze, test)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
        with:
          flutter-version: 3.38.5
          channel: stable
      - run: flutter pub get
      - run: flutter analyze
      - run: flutter test
```

- [ ] **Step 3: Verify locally one more time**: from `mobile/`, `flutter analyze` and `flutter test` (all tests pass).

- [ ] **Step 4: Commit**
```bash
git add .github/workflows/ci.yml mobile/.gitignore
git -c user.name="ouedraogoissouf2012" -c user.email="adcdevteam2025@gmail.com" commit -m "ci(mobile): add Flutter analyze + test job

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes (coverage check)

- **Onboarding + auth** (spec sous-projet 6) → this PR: register/login/logout/stay-logged-in, fully tested.
- **MVVM + Riverpod + Repository** (ADR) → Views (screens) ↔ ViewModel (`AuthViewModel`) ↔ Repository (`AuthRepository`) ↔ ApiClient. Strict separation respected.
- **Tests** → repository (5), view model (3), widget (1) — behavior-verified with fakes/mocks; no live backend needed for CI.
- **CI** → Flutter job added; generated files committed so CI needs no codegen.

**Out of scope (next sub-project-6 PRs):** scenario picker + free mode, conversation screen (WebRTC LiveKit — needs the agent worker + keys), pronunciation card, debrief screen (consumes `GET /sessions/{id}/debrief`), profile & progress. Each will follow the same MVVM slice pattern. **Token-refresh-on-401 interceptor** is intentionally deferred to the PR that first hits protected endpoints heavily (sessions); for auth-only flows the stored access token suffices.
```

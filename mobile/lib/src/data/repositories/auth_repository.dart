import '../../core/config/app_config.dart';
import '../../core/network/api_client.dart';
import '../../core/network/api_exception.dart';
import '../../core/network/token_refresher.dart';
import '../../core/storage/token_storage.dart';
import '../models/app_user.dart';
import '../models/auth_tokens.dart';

class AuthRepository {
  AuthRepository(this._api, this._storage, [TokenRefresher? refresher])
    : _refresher = refresher ?? sharedTokenRefresher(_api, _storage);

  final ApiClient _api;
  final TokenStorage _storage;

  /// Shared with [AuthenticatedApiClient] by default (see
  /// [sharedTokenRefresher]) so an explicit refresh() here and a 401-triggered
  /// refresh over there collapse onto ONE single-flight `/auth/refresh` and
  /// honour the same logout coordination (#316).
  final TokenRefresher _refresher;

  Future<AppUser> register({
    required String email,
    required String password,
    String nativeLanguage = AppConfig.defaultNativeLanguage,
  }) async {
    final json = await _api.postJson(
      '/auth/register',
      body: {
        'email': email,
        'password': password,
        'native_language': nativeLanguage,
      },
    );
    return _persistAndExtractUser(json);
  }

  Future<AppUser> login({
    required String email,
    required String password,
  }) async {
    final json = await _api.postJson(
      '/auth/login',
      body: {'email': email, 'password': password},
    );
    return _persistAndExtractUser(json);
  }

  Future<AppUser?> currentUser() async {
    final token = await _storage.readAccessToken();
    if (token == null) return null;
    try {
      final json = await _api.getJson('/auth/me', bearer: token);
      return AppUser.fromJson(json);
    } on ApiException catch (e) {
      if (e.statusCode != 401) rethrow;
      try {
        return await refresh();
      } catch (_) {
        return null;
      }
    }
  }

  Future<AppUser> refresh() async {
    final json = await _refresher.refresh();
    return AppUser.fromJson(json['user'] as Map<String, dynamic>);
  }

  Future<void> logout() async {
    final refreshToken = await _storage.readRefreshToken();
    try {
      if (refreshToken != null) {
        await _api.postJson(
          '/auth/logout',
          body: {'refresh_token': refreshToken},
        );
      }
    } finally {
      // #316: invalidates + clears as ONE step the shared TokenRefresher
      // treats as uninterruptible relative to any refresh's own save (see
      // TokenRefresher.invalidateAndClear) — so a refresh racing this call,
      // wherever it happens to be, can never resurrect the session logout()
      // just ended.
      await _refresher.invalidateAndClear();
    }
  }

  Future<AppUser> _persistAndExtractUser(Map<String, dynamic> json) async {
    final tokens = AuthTokens.fromJson(json);
    await _storage.save(
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
    );
    return AppUser.fromJson(json['user'] as Map<String, dynamic>);
  }
}

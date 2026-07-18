import '../../core/config/app_config.dart';
import '../../core/network/api_client.dart';
import '../../core/network/api_exception.dart';
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
    final refresh = await _storage.readRefreshToken();
    if (refresh == null) {
      await _storage.clear();
      throw const ApiException(
        statusCode: 401,
        code: 'AuthenticationError',
        message: 'Not authenticated',
      );
    }

    try {
      final json = await _api.postJson(
        '/auth/refresh',
        body: {'refresh_token': refresh},
      );
      return _persistAndExtractUser(json);
    } catch (_) {
      await _storage.clear();
      rethrow;
    }
  }

  Future<void> logout() async {
    final refresh = await _storage.readRefreshToken();
    try {
      if (refresh != null) {
        await _api.postJson('/auth/logout', body: {'refresh_token': refresh});
      }
    } finally {
      await _storage.clear();
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

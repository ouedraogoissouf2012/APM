import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract class TokenStorage {
  Future<void> save({
    required String accessToken,
    required String refreshToken,
  });
  Future<String?> readAccessToken();
  Future<String?> readRefreshToken();
  Future<void> clear();
}

/// Web limitation (#318, evaluated — not fixed here): the access/refresh
/// tokens this stores are protected by the SAME underlying
/// `flutter_secure_storage` AES key as [SecureKeyValueStore] — see that
/// class's doc comment for the verified, detailed explanation of why no
/// `WebOptions(wrapKey: ...)` was added and what web actually protects
/// against today (passive access, not DevTools/XSS).
class SecureTokenStorage implements TokenStorage {
  SecureTokenStorage([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;
  static const _access = 'access_token';
  static const _refresh = 'refresh_token';

  @override
  Future<void> save({
    required String accessToken,
    required String refreshToken,
  }) async {
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

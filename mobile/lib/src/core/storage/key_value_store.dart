import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// A tiny key-value seam so secure-storage-backed persistence (the offline
/// turn queue, the voice-take encryption key) is injectable and testable
/// without the secure-storage platform channel.
abstract class KeyValueStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);

  /// Removes [key], if present.
  Future<void> delete(String key);
}

/// Real store backed by the app's existing secure-storage dependency (web+native).
class SecureKeyValueStore implements KeyValueStore {
  SecureKeyValueStore([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

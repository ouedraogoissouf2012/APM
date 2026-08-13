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
///
/// Web limitation (#318, evaluated — not fixed here): without
/// `WebOptions(wrapKey: ...)`, `flutter_secure_storage`'s web backend
/// generates the AES-256 key, EXPORTS it, and writes it to `localStorage` as
/// plaintext base64 (verified against the resolved flutter_secure_storage_web
/// 2.1.1: `_getEncryptionKey` in lib/flutter_secure_storage_web.dart —
/// `useWrapKey` false branch calls `crypto.subtle.exportKey('raw', ...)` and
/// stores the result directly, lines ~164-191). `WebOptions(wrapKey: ...)`
/// was NOT added: it needs a wrapping secret, and this app has no such
/// secret that isn't ITSELF embedded in the client-side web bundle — a
/// hardcoded wrapKey is exactly as readable via DevTools as the key it would
/// wrap, so it raises no bar against the threat #226 names (DevTools/XSS). A
/// genuine fix means not persisting long-lived secrets client-side on web AT
/// ALL (e.g. HttpOnly server-set cookies for tokens instead of Bearer tokens
/// in storage) — a different auth architecture, out of scope here. What this
/// store still buys on web: protection against PASSIVE access to the stored
/// data (reading the browser profile/localStorage files without executing
/// the page's JS) — not against a live DevTools session or an XSS payload
/// running in the page, both of which can read `localStorage` and drive
/// `crypto.subtle` exactly as the app does.
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

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';

import '../storage/key_value_store.dart';
import 'voice_take_store.dart';

/// Wraps any [VoiceTakeStore] to encrypt the raw learner audio AT REST (#226):
/// today it is stored as PLAINTEXT — a native file or an IndexedDB record —
/// readable by anyone with DevTools access or a stolen/shared device. This
/// encrypts every take with AES-256-GCM before it reaches [_inner], and
/// decrypts on read.
///
/// Key handling: a random 256-bit key is generated on first use and held in
/// the platform's secure keystore (Keychain / Android Keystore / ... via
/// [KeyValueStore] — the same seam the offline turn queue uses), never in
/// app code or plain shared-prefs. [eraseAll] destroys
/// this key in addition to forwarding the erase: any ciphertext bytes that
/// somehow survive a physical delete become permanently unreadable
/// (crypto-shredding) — a backstop for the physical purge, not a substitute
/// for it.
///
/// A take this store cannot decrypt — a legacy PLAINTEXT take saved before
/// this fix, corrupt bytes, or one encrypted under a since-erased key — is
/// treated as absent (not a crash) and physically purged via
/// [VoiceTakeStore.deleteSkill], mirroring how [TtlVoiceTakeStore] treats a
/// stale take: [_inner]'s own "write baseline only if absent" rule would
/// otherwise keep refusing to replace it.
///
/// Uses `package:cryptography`, which selects the Web Crypto API
/// (`crypto.subtle`) on the browser build and a pure-Dart implementation on
/// native — neither path uses fixed-width 64-bit `ByteData` operations, which
/// throw `UnsupportedError` on the web build (JS has no 64-bit int; see
/// [TtlVoiceTakeStore]'s own header encoding for the same constraint).
///
/// Every ciphertext also carries the skill as AES-GCM associated data
/// (#320) — see [_aad] — so a ciphertext can't be silently substituted for a
/// DIFFERENT skill's, even though every skill shares the same key.
class EncryptedVoiceTakeStore implements VoiceTakeStore, SkillEnumerator {
  EncryptedVoiceTakeStore(
    this._inner, {
    KeyValueStore? keyStorage,
    AesGcm? algorithm,
  })  : _keyStorage = keyStorage ?? SecureKeyValueStore(),
        _algorithm = algorithm ?? AesGcm.with256bits();

  final VoiceTakeStore _inner;
  final KeyValueStore _keyStorage;
  final AesGcm _algorithm;

  static const _keyStorageKey = 'voice_take_encryption_key_v1';

  SecretKey? _cachedKey;

  // Serialises key read-or-create against key erase. Without this, two
  // concurrent FIRST-EVER calls (e.g. takesFor for two different skills at a
  // cold start, before any key exists) could each generate and persist a
  // DIFFERENT random key — the loser's in-memory _cachedKey would then
  // silently disagree with what's actually on disk. Mirrors
  // SecureOfflineTurnQueue's own read-modify-write lock.
  Future<void> _keyLock = Future<void>.value();

  Future<T> _synchronized<T>(Future<T> Function() action) {
    final completer = Completer<T>();
    _keyLock = _keyLock.then((_) async {
      try {
        completer.complete(await action());
      } catch (e, s) {
        completer.completeError(e, s);
      }
    });
    return completer.future;
  }

  @override
  Future<void> saveTake(String skill, Uint8List bytes) async {
    final key = await _keyOrCreate();
    final box = await _algorithm.encrypt(bytes, secretKey: key, aad: _aad(skill));
    await _inner.saveTake(skill, box.concatenation());
  }

  @override
  Future<VoiceTakes?> takesFor(String skill) async {
    final takes = await _inner.takesFor(skill);
    if (takes == null) return null;
    final key = await _keyOrCreate();
    final aad = _aad(skill);
    final baseline = await _decryptOrNull(takes.baseline, key, aad);
    final latest = await _decryptOrNull(takes.latest, key, aad);
    if (baseline == null || latest == null) {
      // At least one half is undecryptable — purge so a later save can start
      // a genuinely fresh baseline instead of being blocked by leftover bytes
      // the underlying store still thinks are "the baseline".
      await _inner.deleteSkill(skill);
      return null;
    }
    return VoiceTakes(baseline: baseline, latest: latest);
  }

  @override
  Future<void> eraseAll() async {
    await _synchronized(() async {
      _cachedKey = null;
      await _keyStorage.delete(_keyStorageKey);
    });
    await _inner.eraseAll();
  }

  @override
  Future<void> deleteSkill(String skill) => _inner.deleteSkill(skill);

  @override
  Future<Set<String>> knownSkills() async {
    final inner = _inner;
    // Defensive: only meaningful if [_inner] happens to support enumeration
    // (it does in production — see persistent_voice_take_store*.dart — but a
    // test double standing in for it might not); an empty result just means
    // the startup sweep (#321) that consumes this finds nothing to check.
    if (inner is SkillEnumerator) return (inner as SkillEnumerator).knownSkills();
    return const {};
  }

  Future<SecretKey> _keyOrCreate() {
    final cached = _cachedKey;
    if (cached != null) return Future.value(cached);
    return _synchronized(() async {
      // Re-check: another caller may have resolved the key while this one
      // was waiting for the lock.
      final cached = _cachedKey;
      if (cached != null) return cached;
      final stored = await _keyStorage.read(_keyStorageKey);
      if (stored != null) {
        return _cachedKey = SecretKey(base64Decode(stored));
      }
      final fresh = await _algorithm.newSecretKey();
      final bytes = await fresh.extractBytes();
      await _keyStorage.write(_keyStorageKey, base64Encode(bytes));
      return _cachedKey = fresh;
    });
  }

  Future<Uint8List?> _decryptOrNull(
    Uint8List stored,
    SecretKey key,
    List<int> aad,
  ) async {
    try {
      final box = SecretBox.fromConcatenation(
        stored,
        nonceLength: _algorithm.nonceLength,
        macLength: _algorithm.macAlgorithm.macLength,
      );
      final clear = await _algorithm.decrypt(box, secretKey: key, aad: aad);
      return Uint8List.fromList(clear);
    } catch (_) {
      return null;
    }
  }

  /// Binds every ciphertext to the key it belongs to (#320): without this,
  /// the same key encrypts every skill identically, so a raw storage-level
  /// write (DevTools against IndexedDB, a compromised backup) can copy one
  /// skill's ciphertext into another's slot and the GCM tag still verifies —
  /// the app would silently replay the wrong recording as proof for a
  /// DIFFERENT skill. In the real composed chain (see persistent_voice_take_
  /// store*.dart) [skill] here already arrives scoped by user id
  /// (UserScopedVoiceTakeStore, #319), so this transitively binds the user
  /// too — a same-skill ciphertext can't be replayed across accounts either.
  /// Binding to the key alone (not key+slot) is a deliberate, narrower
  /// scope: distinguishing baseline from latest would need [_inner] to
  /// expose whether a baseline already exists before this write decides its
  /// AAD, which would add a method to [VoiceTakeStore] — and two tests
  /// outside this fix's own file scope (voice_privacy_screen_test.dart,
  /// conversation_view_model_test.dart) implement that interface directly
  /// and would stop compiling. Key-level binding still defeats the concrete
  /// cross-skill/cross-account substitution this issue describes; a
  /// same-skill baseline/latest swap is not covered — tracked separately.
  ///
  /// Uses [safeStorageKey] — the SAME normalisation [FileVoiceTakeStore] and
  /// [KvVoiceTakeStore] apply to their filenames/KV keys — rather than
  /// [skill] verbatim. This is required, not cosmetic: [TtlVoiceTakeStore.
  /// sweepExpired] (#321) re-enters [takesFor] with the ALREADY-safe stem
  /// [SkillEnumerator.knownSkills] reports (the file system can only ever
  /// hand back the post-transform name), which differs from the raw key
  /// [saveTake] was originally called with whenever that key contains a
  /// character the transform rewrites — true for every key today, since
  /// #319 always prefixes with `'$userId:'`. Without normalising first, a
  /// sweep-triggered read would compute a DIFFERENT AAD than the one used
  /// at save time, fail GCM authentication, and wrongly purge a perfectly
  /// fresh take on every app restart. [safeStorageKey] is idempotent, so
  /// normalising the raw key here computes the exact same AAD as
  /// normalising the already-safe one.
  ///
  /// A ciphertext produced before this fix (no AAD) or copied from a
  /// different skill fails to decrypt under the new AAD and is treated the
  /// same as any other undecryptable take: absent, then physically purged
  /// (see [takesFor]) — a clean, automatic migration/invalidation, not a
  /// crash.
  List<int> _aad(String skill) => utf8.encode(safeStorageKey(skill));
}

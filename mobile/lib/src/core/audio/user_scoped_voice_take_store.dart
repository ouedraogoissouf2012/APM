import 'dart:typed_data';

import '../storage/key_value_store.dart';
import 'voice_take_store.dart';

/// Optional capability [AuthViewModel] uses to keep a [VoiceTakeStore]'s
/// per-user key-scoping and logout-purge tracking (#319) in sync with the
/// active session. Kept separate from [VoiceTakeStore] itself so ordinary
/// callers/tests never need to know it exists — only the auth layer, which
/// is the one place that knows who's currently signed in.
abstract class VoiceTakeUserSession {
  /// Call whenever the active session changes: after [build] resolves a
  /// user, after a successful login/register, and once more (with `null`)
  /// once logout's purge attempt has run. `null` means signed out — every
  /// [VoiceTakeStore] call while signed out is refused (see
  /// [UserScopedVoiceTakeStore]) rather than silently operating under a
  /// stale identity.
  void setCurrentUser(int? userId);
}

/// Wraps any [VoiceTakeStore] to close two gaps in an app used on shared
/// devices — school/family computers, per voice_consent.dart's own framing
/// (#319):
///
/// 1. **Cross-account replay.** The wrapped store is keyed by skill ALONE
///    (e.g. `job_interview.baseline`) — the same key on every account. If
///    learner A's takes for a skill are still on disk when learner B opens
///    the SAME skill (shared scenario slugs are the norm, not the
///    exception), B hears A's voice. This wrapper prefixes every key with
///    the CURRENT user id, so two accounts never share a key regardless of
///    what physically survives on disk.
///
/// 2. **A failed logout purge leaving stale takes readable.** [AuthViewModel]
///    already calls [eraseAll] on logout, best-effort (#226) — a transient
///    Keystore/IndexedDB failure must never strand the learner unable to log
///    out. But "best-effort" previously meant a FAILED purge left that
///    user's takes fully readable forever. This wrapper remembers (durably —
///    see [_pendingPurgeKey]) EVERY user whose purge did not confirm success
///    (a set, not a single slot: a second, unrelated user's failure must not
///    silently un-block an earlier one — see [_pendingPurgeUserIds]), and
///    refuses [takesFor] for any of them until a LATER [eraseAll] actually
///    succeeds — so even if that learner is the one who logs back in on
///    this device, their "erased" data stays hidden rather than quietly
///    reappearing. Key-scoping alone (point 1) already stops a DIFFERENT
///    learner from ever reaching this data; this is the narrower,
///    same-account backstop the issue also asks for.
///
/// Deliberately does NOT retry a failed purge proactively (e.g. on the next
/// [setCurrentUser] for a different user): [eraseAll] wipes the WHOLE
/// underlying store — every account's takes, not just the current one, a
/// pre-existing property of [VoiceTakeStore.eraseAll] this wrapper does not
/// change — and retrying it after a new user has already started saving
/// their own takes would destroy that new, unrelated data. The next
/// explicit [eraseAll] for a SAME tainted user (their own next logout, or
/// "Erase my voice data" in the privacy screen) is what clears them — and
/// because [eraseAll] really does wipe everything, ANY successful call to
/// it, by any user, clears EVERY pending taint at once, not just the
/// caller's own.
class UserScopedVoiceTakeStore implements VoiceTakeStore, VoiceTakeUserSession {
  UserScopedVoiceTakeStore(this._inner, {KeyValueStore? pendingPurgeStorage})
      : _pendingPurgeStorage = pendingPurgeStorage ?? SecureKeyValueStore();

  final VoiceTakeStore _inner;
  final KeyValueStore _pendingPurgeStorage;

  // v2 (a comma-separated SET of user ids, not a single id) because a second
  // user's failed purge must not silently overwrite/un-block an earlier,
  // unrelated one's pending taint.
  static const _pendingPurgeKey = 'voice_take_pending_purge_user_ids_v2';

  int? _currentUserId;

  // Loaded lazily from [_pendingPurgeStorage] (survives an app restart,
  // unlike a plain in-memory set would — the shared-device scenario this
  // exists for plausibly spans a full app close/reopen between accounts).
  Set<int>? _pendingPurgeUserIds;

  @override
  void setCurrentUser(int? userId) {
    _currentUserId = userId;
  }

  @override
  Future<void> saveTake(String skill, Uint8List bytes) =>
      _inner.saveTake(_scoped(_requireCurrentUser(), skill), bytes);

  @override
  Future<VoiceTakes?> takesFor(String skill) async {
    final userId = _requireCurrentUser();
    if ((await _pendingPurges()).contains(userId)) return null; // #319: blocked
    return _inner.takesFor(_scoped(userId, skill));
  }

  @override
  Future<void> eraseAll() async {
    final userId = _currentUserId;
    try {
      await _inner.eraseAll();
      // eraseAll() wipes EVERYTHING (there is no per-user scope at [_inner]'s
      // level), so every previously pending purge — whoever's it was — is
      // now moot too, not just this user's.
      await _clearPendingPurges();
    } catch (_) {
      if (userId != null) await _addPendingPurge(userId);
      rethrow;
    }
  }

  @override
  Future<void> deleteSkill(String skill) =>
      _inner.deleteSkill(_scoped(_requireCurrentUser(), skill));

  int _requireCurrentUser() {
    final userId = _currentUserId;
    if (userId == null) {
      throw StateError(
        'VoiceTakeStore accessed with no signed-in user (#319) — '
        'AuthViewModel must call setCurrentUser before this store is used.',
      );
    }
    return userId;
  }

  Future<Set<int>> _pendingPurges() async {
    final cached = _pendingPurgeUserIds;
    if (cached != null) return cached;
    final raw = await _pendingPurgeStorage.read(_pendingPurgeKey);
    final loaded = _parse(raw);
    // Re-check: a concurrent eraseAll() (_addPendingPurge/_clearPendingPurges)
    // may have resolved and written its OWN, authoritative result while this
    // read was in flight. Without this, the read above — now stale — would
    // unconditionally overwrite that fresh write, silently un-blocking a
    // user whose purge just failed (or discarding a fresh clear) for the
    // rest of this app session. Mirrors EncryptedVoiceTakeStore._keyOrCreate's
    // own re-check-after-await guard for the identical class of race.
    final recheck = _pendingPurgeUserIds;
    if (recheck != null) return recheck;
    return _pendingPurgeUserIds = loaded;
  }

  Future<void> _addPendingPurge(int userId) async {
    final current = await _pendingPurges();
    final updated = {...current, userId};
    await _pendingPurgeStorage.write(_pendingPurgeKey, updated.join(','));
    _pendingPurgeUserIds = updated;
  }

  Future<void> _clearPendingPurges() async {
    await _pendingPurgeStorage.delete(_pendingPurgeKey);
    _pendingPurgeUserIds = const {};
  }

  static Set<int> _parse(String? raw) {
    if (raw == null || raw.isEmpty) return const {};
    return raw
        .split(',')
        .map(int.tryParse)
        .whereType<int>() // defensive: ignore a malformed/corrupt entry
        .toSet();
  }

  static String _scoped(int userId, String skill) => '$userId:$skill';
}

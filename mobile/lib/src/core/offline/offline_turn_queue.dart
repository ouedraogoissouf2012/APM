import 'dart:async';
import 'dart:convert';

import '../storage/key_value_store.dart';
import 'pending_turn.dart';

export '../storage/key_value_store.dart'
    show KeyValueStore, SecureKeyValueStore;

/// A persisted FIFO queue of turns waiting to be sent (offline-first, #127).
/// Survives app restarts so a turn spoken offline is never lost; replayed in
/// order on reconnect.
abstract class OfflineTurnQueue {
  Future<void> enqueue(PendingTurn turn);
  Future<List<PendingTurn>> pending();

  /// Removes the turn with [idempotencyKey] once it has been sent successfully.
  Future<void> remove(String idempotencyKey);
}

/// Optional capability AuthViewModel uses to keep [OfflineTurnQueue]'s
/// per-user key-scoping and logout-purge (#349, mirrors VoiceTakeUserSession
/// / #319) in sync with the active session. Kept separate from
/// [OfflineTurnQueue] itself so ordinary callers/tests never need to know it
/// exists — only the auth layer, which is the one place that knows who's
/// currently signed in.
abstract class OfflineTurnQueueUserSession {
  /// Call whenever the active session changes: after AuthViewModel.build
  /// resolves a user, after a successful login/register, and once more
  /// (with `null`) once logout's purge attempt has run. `null` means signed
  /// out — every [OfflineTurnQueue] call while signed out is refused (see
  /// [SecureOfflineTurnQueue]) rather than silently reading/writing under a
  /// stale or shared key.
  void setCurrentUser(int? userId);

  /// Deletes every turn queued under the CURRENTLY active user (a no-op if
  /// no user is set). Best-effort, mirroring the voice-take purge this
  /// pairs with in AuthViewModel.logout: a spoken utterance
  /// ([PendingTurn.text], #349) must not outlive this user's session on a
  /// shared device.
  Future<void> purgeCurrentUser();
}

/// Persisted queue (one JSON array per signed-in user) over a [KeyValueStore].
///
/// Keyed by user id (#349): the queue used to live under one fixed key
/// shared by every account on the device, so a learner's un-sent turns —
/// [PendingTurn.text] is their own spoken utterance — stayed readable by (and
/// on reconnect got silently synced as) the NEXT account signing in on a
/// shared device. [setCurrentUser] must be called (by AuthViewModel, the one
/// place that knows who's signed in) before [enqueue]/[pending]/[remove] are
/// used; each then only ever reads/writes the CURRENT user's own key —
/// accessing them with no user set is a programming error and throws rather
/// than silently falling back to a shared key.
///
/// Unlike [UserScopedVoiceTakeStore]'s wrapper shape, this scoping lives
/// directly on the concrete queue rather than a separate wrapper class: the
/// queue is one whole document (unlike a voice take, there's no per-call
/// argument — a skill — to prefix), so the queue itself is the thing that's
/// user-scoped, not an individual entry within it.
///
/// Pre-existing turns queued under the old, unscoped key (installs from
/// before #349) are not migrated: which user they belong to can no longer be
/// determined, and guessing wrong would replay a stranger's words into a
/// DIFFERENT learner's conversation under that learner's identity — worse
/// than the bounded, one-time loss of leaving them unread.
class SecureOfflineTurnQueue
    implements OfflineTurnQueue, OfflineTurnQueueUserSession {
  SecureOfflineTurnQueue(this._store);

  final KeyValueStore _store;
  static const _keyPrefix = 'offline_turn_queue';

  int? _currentUserId;

  // Serialises read-modify-write ops. enqueue (a new turn failing) can otherwise
  // race a remove (a sync draining the queue): both read the same JSON, mutate,
  // and write — the second clobbers the first, silently losing a turn. Chaining
  // on a single future makes each mutation see the previous one's result.
  Future<void> _lock = Future<void>.value();

  Future<T> _synchronized<T>(Future<T> Function() action) {
    final completer = Completer<T>();
    _lock = _lock.then((_) async {
      try {
        completer.complete(await action());
      } catch (e, s) {
        completer.completeError(e, s);
      }
    });
    return completer.future;
  }

  @override
  void setCurrentUser(int? userId) {
    _currentUserId = userId;
  }

  int _requireCurrentUser() {
    final userId = _currentUserId;
    if (userId == null) {
      throw StateError(
        'OfflineTurnQueue accessed with no signed-in user (#349) — '
        'AuthViewModel must call setCurrentUser before this queue is used.',
      );
    }
    return userId;
  }

  static String _keyFor(int userId) => '$_keyPrefix:$userId';

  Future<List<PendingTurn>> _read(String key) async {
    final raw = await _store.read(key);
    if (raw == null || raw.isEmpty) return [];
    final list = jsonDecode(raw) as List;
    return list
        .map((e) => PendingTurn.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> _write(String key, List<PendingTurn> turns) =>
      _store.write(key, jsonEncode([for (final t in turns) t.toJson()]));

  @override
  Future<void> enqueue(PendingTurn turn) => _synchronized(() async {
    final key = _keyFor(_requireCurrentUser());
    final turns = await _read(key)
      ..add(turn);
    await _write(key, turns);
  });

  @override
  Future<List<PendingTurn>> pending() =>
      _synchronized(() => _read(_keyFor(_requireCurrentUser())));

  @override
  Future<void> remove(String idempotencyKey) => _synchronized(() async {
    final key = _keyFor(_requireCurrentUser());
    final turns = await _read(key)
      ..removeWhere((t) => t.idempotencyKey == idempotencyKey);
    await _write(key, turns);
  });

  @override
  Future<void> purgeCurrentUser() => _synchronized(() async {
    final userId = _currentUserId;
    if (userId == null) return;
    await _store.delete(_keyFor(userId));
  });
}

import 'dart:async';
import 'dart:convert';

import '../storage/key_value_store.dart';
import 'pending_turn.dart';

export '../storage/key_value_store.dart' show KeyValueStore, SecureKeyValueStore;

/// A persisted FIFO queue of turns waiting to be sent (offline-first, #127).
/// Survives app restarts so a turn spoken offline is never lost; replayed in
/// order on reconnect.
abstract class OfflineTurnQueue {
  Future<void> enqueue(PendingTurn turn);
  Future<List<PendingTurn>> pending();

  /// Removes the turn with [idempotencyKey] once it has been sent successfully.
  Future<void> remove(String idempotencyKey);
}

/// Persisted queue (one JSON array under a single key) over a [KeyValueStore].
class SecureOfflineTurnQueue implements OfflineTurnQueue {
  SecureOfflineTurnQueue(this._store);

  final KeyValueStore _store;
  static const _key = 'offline_turn_queue';

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

  Future<List<PendingTurn>> _read() async {
    final raw = await _store.read(_key);
    if (raw == null || raw.isEmpty) return [];
    final list = jsonDecode(raw) as List;
    return list
        .map((e) => PendingTurn.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> _write(List<PendingTurn> turns) =>
      _store.write(_key, jsonEncode([for (final t in turns) t.toJson()]));

  @override
  Future<void> enqueue(PendingTurn turn) => _synchronized(() async {
    final turns = await _read()..add(turn);
    await _write(turns);
  });

  @override
  Future<List<PendingTurn>> pending() => _synchronized(_read);

  @override
  Future<void> remove(String idempotencyKey) => _synchronized(() async {
    final turns = await _read()
      ..removeWhere((t) => t.idempotencyKey == idempotencyKey);
    await _write(turns);
  });
}

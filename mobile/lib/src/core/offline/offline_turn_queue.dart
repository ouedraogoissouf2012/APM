import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'pending_turn.dart';

/// A tiny key-value seam so the queue's persistence is injectable and testable
/// without the secure-storage platform channel.
abstract class KeyValueStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
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
}

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
  Future<void> enqueue(PendingTurn turn) async {
    final turns = await _read()..add(turn);
    await _write(turns);
  }

  @override
  Future<List<PendingTurn>> pending() => _read();

  @override
  Future<void> remove(String idempotencyKey) async {
    final turns = await _read()
      ..removeWhere((t) => t.idempotencyKey == idempotencyKey);
    await _write(turns);
  }
}

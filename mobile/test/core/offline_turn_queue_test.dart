import 'dart:convert';

import 'package:apm/src/core/offline/offline_turn_queue.dart';
import 'package:apm/src/core/offline/pending_turn.dart';
import 'package:flutter_test/flutter_test.dart';

/// In-memory key-value store so the queue's persistence is testable.
class _InMemoryStore implements KeyValueStore {
  final Map<String, String> data = {};

  @override
  Future<String?> read(String key) async => data[key];

  @override
  Future<void> write(String key, String value) async => data[key] = value;
}

/// A store that yields the event loop between read and write, so two concurrent
/// read-modify-write operations WOULD interleave and clobber each other unless
/// the queue serialises them.
class _YieldingStore implements KeyValueStore {
  final Map<String, String> data = {};

  @override
  Future<String?> read(String key) async {
    await Future<void>.delayed(Duration.zero);
    return data[key];
  }

  @override
  Future<void> write(String key, String value) async {
    await Future<void>.delayed(Duration.zero);
    data[key] = value;
  }
}

PendingTurn _turn(String key, {int session = 1, String text = 'hi'}) =>
    PendingTurn(sessionId: session, text: text, idempotencyKey: key);

void main() {
  late SecureOfflineTurnQueue queue;
  late _InMemoryStore store;

  setUp(() {
    store = _InMemoryStore();
    queue = SecureOfflineTurnQueue(store);
  });

  test('enqueue then pending returns the turns in order', () async {
    await queue.enqueue(_turn('a'));
    await queue.enqueue(_turn('b'));

    final pending = await queue.pending();
    expect(pending.map((t) => t.idempotencyKey), ['a', 'b']);
  });

  test('remove drops the matching turn only', () async {
    await queue.enqueue(_turn('a'));
    await queue.enqueue(_turn('b'));

    await queue.remove('a');

    final pending = await queue.pending();
    expect(pending.map((t) => t.idempotencyKey), ['b']);
  });

  test('the queue is persisted (survives a new instance on same storage)', () async {
    await queue.enqueue(_turn('a', text: 'I like sports'));

    final reopened = SecureOfflineTurnQueue(store);
    final pending = await reopened.pending();
    expect(pending.single.text, 'I like sports');
  });

  test('an empty/absent queue reads as empty', () async {
    expect(await queue.pending(), isEmpty);
  });

  test('turns round-trip through JSON', () {
    final t = _turn('k', session: 7, text: 'hello');
    final back = PendingTurn.fromJson(jsonDecode(jsonEncode(t.toJson())));
    expect(back.sessionId, 7);
    expect(back.text, 'hello');
    expect(back.idempotencyKey, 'k');
  });

  test('concurrent enqueue and remove do not clobber each other (no lost turn)',
      () async {
    // A new turn failing (enqueue) can race a sync draining the queue (remove).
    // With a yielding store, unserialised read-modify-write would lose one; the
    // queue's internal lock must prevent that.
    final q = SecureOfflineTurnQueue(_YieldingStore());
    await q.enqueue(_turn('a'));

    await Future.wait([q.enqueue(_turn('b')), q.remove('a')]);

    final pending = await q.pending();
    // 'a' removed and 'b' added — neither operation lost.
    expect(pending.map((t) => t.idempotencyKey), ['b']);
  });
}

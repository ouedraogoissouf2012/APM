import 'dart:async';

import 'package:apm/src/core/offline/connectivity_controller.dart';
import 'package:apm/src/core/offline/offline_turn_queue.dart';
import 'package:apm/src/core/offline/offline_turn_sync.dart';
import 'package:apm/src/core/offline/pending_turn.dart';
import 'package:apm/src/core/offline/providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _InMemoryQueue implements OfflineTurnQueue {
  final List<PendingTurn> turns = [];

  @override
  Future<void> enqueue(PendingTurn turn) async => turns.add(turn);

  @override
  Future<List<PendingTurn>> pending() async => List.of(turns);

  @override
  Future<void> remove(String key) async =>
      turns.removeWhere((t) => t.idempotencyKey == key);
}

/// A sync that "sends" everything (clears the queue) or nothing, on demand.
/// Counts calls and can be held open (via [gate]) to test re-entrancy.
class _FakeSync implements OfflineTurnSync {
  _FakeSync(this._queue);
  final _InMemoryQueue _queue;
  bool succeeds = true;
  int calls = 0;
  Completer<void>? gate;

  @override
  Future<int> sync() async {
    calls++;
    if (gate != null) await gate!.future;
    if (!succeeds) return 0;
    final n = _queue.turns.length;
    _queue.turns.clear();
    return n;
  }
}

void main() {
  late _InMemoryQueue queue;
  late _FakeSync sync;
  late ProviderContainer container;

  setUp(() {
    queue = _InMemoryQueue();
    sync = _FakeSync(queue);
    container = ProviderContainer(
      overrides: [
        offlineTurnQueueProvider.overrideWithValue(queue),
        offlineTurnSyncProvider.overrideWithValue(sync),
      ],
    );
    addTearDown(container.dispose);
  });

  test('recordFailedTurn queues the turn under the SAME key it failed with '
      '(#313)', () async {
    final ctrl = container.read(connectivityControllerProvider.notifier);

    // The caller (reply_playback.dart) always passes the exact key the failed
    // attempt was sent with — recordFailedTurn must not regenerate a new one,
    // or the server would run the turn twice (once per key) on replay.
    await ctrl.recordFailedTurn(1, 'I like sports', idempotencyKey: 'k1');

    final state = container.read(connectivityControllerProvider);
    expect(state.online, isFalse);
    expect(state.pendingCount, 1);
    expect(queue.turns.single.text, 'I like sports');
    expect(queue.turns.single.idempotencyKey, 'k1');
  });

  test('syncPending clears the queue and returns online', () async {
    final ctrl = container.read(connectivityControllerProvider.notifier);
    await ctrl.recordFailedTurn(1, 'a', idempotencyKey: 'k1');
    await ctrl.recordFailedTurn(1, 'b', idempotencyKey: 'k2');

    await ctrl.syncPending();

    final state = container.read(connectivityControllerProvider);
    expect(state.online, isTrue);
    expect(state.pendingCount, 0);
  });

  test('syncPending stays offline when nothing could be sent', () async {
    final ctrl = container.read(connectivityControllerProvider.notifier);
    await ctrl.recordFailedTurn(1, 'a', idempotencyKey: 'k1');
    sync.succeeds = false; // still offline

    await ctrl.syncPending();

    final state = container.read(connectivityControllerProvider);
    expect(state.online, isFalse);
    expect(state.pendingCount, 1);
  });

  test('refresh loads the current pending count', () async {
    await queue.enqueue(
      const PendingTurn(sessionId: 1, text: 'x', idempotencyKey: 'k'),
    );
    final ctrl = container.read(connectivityControllerProvider.notifier);

    await ctrl.refresh();

    expect(container.read(connectivityControllerProvider).pendingCount, 1);
  });

  test('a concurrent syncPending is ignored while one is in flight', () async {
    await queue.enqueue(_turnFor(1));
    final ctrl = container.read(connectivityControllerProvider.notifier);
    sync.gate = Completer<void>(); // hold the first sync open

    final first = ctrl.syncPending(); // enters sync(), then blocks on the gate
    await Future<void>.delayed(Duration.zero);
    final second = ctrl.syncPending(); // must be a no-op (guarded), not a 2nd sync

    sync.gate!.complete();
    await Future.wait([first, second]);

    expect(sync.calls, 1); // exactly one replay ran despite two triggers
  });
}

PendingTurn _turnFor(int session) =>
    PendingTurn(sessionId: session, text: 'hi', idempotencyKey: 'k$session');

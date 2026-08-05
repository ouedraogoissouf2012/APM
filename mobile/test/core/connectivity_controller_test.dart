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
class _FakeSync implements OfflineTurnSync {
  _FakeSync(this._queue);
  final _InMemoryQueue _queue;
  bool succeeds = true;

  @override
  Future<int> sync() async {
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
    // Deterministic idempotency keys in tests.
    var counter = 0;
    ConnectivityController.keyFactory = (sessionId) => 'key-${counter++}';
    container = ProviderContainer(
      overrides: [
        offlineTurnQueueProvider.overrideWithValue(queue),
        offlineTurnSyncProvider.overrideWithValue(sync),
      ],
    );
    addTearDown(container.dispose);
  });

  test('recordFailedTurn queues the turn and goes offline', () async {
    final ctrl = container.read(connectivityControllerProvider.notifier);

    await ctrl.recordFailedTurn(1, 'I like sports');

    final state = container.read(connectivityControllerProvider);
    expect(state.online, isFalse);
    expect(state.pendingCount, 1);
    expect(queue.turns.single.text, 'I like sports');
    expect(queue.turns.single.idempotencyKey, 'key-0');
  });

  test('syncPending clears the queue and returns online', () async {
    final ctrl = container.read(connectivityControllerProvider.notifier);
    await ctrl.recordFailedTurn(1, 'a');
    await ctrl.recordFailedTurn(1, 'b');

    await ctrl.syncPending();

    final state = container.read(connectivityControllerProvider);
    expect(state.online, isTrue);
    expect(state.pendingCount, 0);
  });

  test('syncPending stays offline when nothing could be sent', () async {
    final ctrl = container.read(connectivityControllerProvider.notifier);
    await ctrl.recordFailedTurn(1, 'a');
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
}

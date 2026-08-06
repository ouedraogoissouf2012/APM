import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'offline_turn_queue.dart';
import 'offline_turn_sync.dart';
import 'pending_turn.dart';
import 'providers.dart';

/// What the UI shows about connectivity (#127). `online` flips to false the
/// moment a turn fails on the network; `pendingCount` is how many turns are
/// queued waiting to be replayed.
class ConnectivityState {
  const ConnectivityState({this.online = true, this.pendingCount = 0});

  final bool online;
  final int pendingCount;

  bool get hasPending => pendingCount > 0;

  ConnectivityState copyWith({bool? online, int? pendingCount}) =>
      ConnectivityState(
        online: online ?? this.online,
        pendingCount: pendingCount ?? this.pendingCount,
      );
}

final connectivityControllerProvider =
    NotifierProvider<ConnectivityController, ConnectivityState>(
      ConnectivityController.new,
    );

/// Owns the offline/pending state and bridges it to the offline queue: a turn
/// that fails on the network is queued here (so it's never lost) and the UI goes
/// offline; a successful sync replays the queue and returns online.
class ConnectivityController extends Notifier<ConnectivityState> {
  /// Injectable so tests get a deterministic idempotency key.
  static String Function(int sessionId) keyFactory =
      (sessionId) => '$sessionId-${DateTime.now().microsecondsSinceEpoch}';

  OfflineTurnQueue get _queue => ref.read(offlineTurnQueueProvider);
  OfflineTurnSync get _sync => ref.read(offlineTurnSyncProvider);

  @override
  ConnectivityState build() => const ConnectivityState();

  /// Loads the current pending count (e.g. on app start).
  Future<void> refresh() async {
    final count = (await _queue.pending()).length;
    state = state.copyWith(pendingCount: count);
  }

  /// Queues a turn that failed on the network and marks the app offline.
  Future<void> recordFailedTurn(int sessionId, String text) async {
    await _queue.enqueue(
      PendingTurn(
        sessionId: sessionId,
        text: text,
        idempotencyKey: keyFactory(sessionId),
      ),
    );
    final count = (await _queue.pending()).length;
    state = ConnectivityState(online: false, pendingCount: count);
  }

  /// Replays the queue; back online when nothing remains.
  Future<void> syncPending() async {
    await _sync.sync();
    final count = (await _queue.pending()).length;
    state = ConnectivityState(online: count == 0, pendingCount: count);
  }
}

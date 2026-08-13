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
  OfflineTurnQueue get _queue => ref.read(offlineTurnQueueProvider);
  OfflineTurnSync get _sync => ref.read(offlineTurnSyncProvider);

  // Guards against overlapping replays: a connectivity flap + a manual "Réessayer"
  // could otherwise start two sync() loops that both fire the same queued turn.
  bool _syncing = false;

  @override
  ConnectivityState build() => const ConnectivityState();

  /// Loads the current pending count (e.g. on app start).
  Future<void> refresh() async {
    final count = (await _queue.pending()).length;
    state = state.copyWith(pendingCount: count);
  }

  /// Queues a turn that failed on the network and marks the app offline.
  ///
  /// [idempotencyKey] MUST be the SAME key the failed attempt was sent with
  /// (#313): the server may have already received and be processing (or have
  /// fully processed) that request when only the response was lost on the
  /// network. Generating a fresh key here would make the replay a genuinely
  /// NEW request, so the server would run the turn a second time — double
  /// LLM call, double transcript entry, double quota charge — instead of the
  /// idempotency layer recognising it as the same request and replaying the
  /// cached result.
  Future<void> recordFailedTurn(
    int sessionId,
    String text, {
    required String idempotencyKey,
  }) async {
    await _queue.enqueue(
      PendingTurn(
        sessionId: sessionId,
        text: text,
        idempotencyKey: idempotencyKey,
      ),
    );
    final count = (await _queue.pending()).length;
    state = ConnectivityState(online: false, pendingCount: count);
  }

  /// Replays the queue; back online when nothing remains. Re-entrant calls (e.g.
  /// a reconnect trigger racing a manual retry) are ignored while a sync is in
  /// flight, so the same queued turn is never replayed twice concurrently.
  Future<void> syncPending() async {
    if (_syncing) return;
    _syncing = true;
    try {
      await _sync.sync();
      final count = (await _queue.pending()).length;
      state = ConnectivityState(online: count == 0, pendingCount: count);
    } finally {
      _syncing = false;
    }
  }
}

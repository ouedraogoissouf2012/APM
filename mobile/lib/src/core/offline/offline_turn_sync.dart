import '../../data/repositories/conversation_repository.dart';
import '../network/api_exception.dart';
import 'offline_turn_queue.dart';

/// Replays queued turns when connectivity returns (#127). Each turn is sent with
/// its idempotency key, so a turn the server already processed (but whose reply
/// was lost) is not duplicated. Removed from the queue only on success; a network
/// failure stops the run so the remaining turns are retried later, in order.
class OfflineTurnSync {
  OfflineTurnSync(this._queue, this._conversation);

  final OfflineTurnQueue _queue;
  final ConversationRepository _conversation;

  /// Replays all pending turns in order. Returns the number sent. Stops early on
  /// a network error (keeps the rest queued); a non-network error (e.g. the
  /// session ended) drops that one turn and continues so it can't block forever.
  Future<int> sync() async {
    var sent = 0;
    for (final turn in await _queue.pending()) {
      try {
        await _conversation.sendTurn(
          turn.sessionId,
          turn.text,
          idempotencyKey: turn.idempotencyKey,
        );
        await _queue.remove(turn.idempotencyKey);
        sent++;
      } on ApiException catch (e) {
        if (_isNetwork(e)) return sent; // still offline — retry the rest later
        // A definitive server rejection: drop this turn so it can't wedge the
        // queue, and move on to the next.
        await _queue.remove(turn.idempotencyKey);
      }
    }
    return sent;
  }

  bool _isNetwork(ApiException e) => e.statusCode == 0 || e.code == 'network';
}

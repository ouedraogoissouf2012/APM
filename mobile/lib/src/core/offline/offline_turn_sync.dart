import '../../data/repositories/conversation_repository.dart';
import '../network/api_exception.dart';
import '../observability/crash_reporter.dart';
import 'offline_turn_queue.dart';

/// Replays queued turns when connectivity returns (#127). Each turn is sent with
/// its idempotency key, so a turn the server already processed (but whose reply
/// was lost) is not duplicated. Removed from the queue only on success; a network
/// failure stops the run so the remaining turns are retried later, in order.
class OfflineTurnSync {
  OfflineTurnSync(this._queue, this._conversation, this._crashReporter);

  final OfflineTurnQueue _queue;
  final ConversationRepository _conversation;
  final CrashReporter _crashReporter;
  int _generation = 0;

  /// Abort an in-flight [sync] so a logout cannot finish posting as the next
  /// account (#429). Safe to call when no sync is running.
  void cancel() => _generation++;

  /// Replays all pending turns in order. Returns the number sent. Stops early and
  /// KEEPS the rest queued on a transient failure (offline, a 5xx, or a 409
  /// "in progress") so nothing is lost; only a DEFINITIVE client error (a 4xx
  /// other than 409 — e.g. the session ended) drops that one turn and continues,
  /// so a permanently-unprocessable turn can't wedge the queue forever.
  Future<int> sync() async {
    var sent = 0;
    final generation = _generation;
    for (final turn in await _queue.pending()) {
      if (_generation != generation) return sent;
      try {
        await _conversation.sendTurn(
          turn.sessionId,
          turn.text,
          idempotencyKey: turn.idempotencyKey,
          practicedAt: turn.practicedAt,
        );
        if (_generation != generation) return sent;
        await _queue.remove(turn.idempotencyKey);
        sent++;
      } on ApiException catch (e) {
        if (_retryLater(e)) return sent; // keep queued, retry later, in order
        // Definitive rejection (#236): the turn is about to disappear with no
        // server-side trace of the learner's utterance either — capture it
        // BEFORE removing, so it isn't lost without a trace on either side.
        _crashReporter.captureError(
          e,
          StackTrace.current,
          context: 'OfflineTurnSync.sync: dropping unrecoverable turn',
          data: {'statusCode': e.statusCode, 'idempotencyKey': turn.idempotencyKey},
        );
        await _queue.remove(turn.idempotencyKey); // definitive: drop and continue
      }
    }
    return sent;
  }

  /// Transient failures that must NOT drop the turn: no connection, a server-side
  /// 5xx, or a 409 (the server is still processing this exact key — retrying
  /// returns the cached reply once it finishes, or reclaims it if that request
  /// crashed). Everything else (4xx) is a definitive rejection.
  bool _retryLater(ApiException e) =>
      e.statusCode == 0 ||
      e.code == 'network' ||
      e.statusCode >= 500 ||
      e.statusCode == 409;
}

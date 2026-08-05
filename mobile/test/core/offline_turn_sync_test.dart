import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/core/offline/offline_turn_queue.dart';
import 'package:apm/src/core/offline/offline_turn_sync.dart';
import 'package:apm/src/core/offline/pending_turn.dart';
import 'package:apm/src/data/repositories/conversation_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockConversation extends Mock implements ConversationRepository {}

class _InMemoryQueue implements OfflineTurnQueue {
  final List<PendingTurn> _turns = [];

  @override
  Future<void> enqueue(PendingTurn turn) async => _turns.add(turn);

  @override
  Future<List<PendingTurn>> pending() async => List.of(_turns);

  @override
  Future<void> remove(String idempotencyKey) async =>
      _turns.removeWhere((t) => t.idempotencyKey == idempotencyKey);
}

PendingTurn _turn(String key) =>
    PendingTurn(sessionId: 1, text: 'hi', idempotencyKey: key);

void main() {
  late _MockConversation conv;
  late _InMemoryQueue queue;
  late OfflineTurnSync sync;

  setUp(() {
    conv = _MockConversation();
    queue = _InMemoryQueue();
    sync = OfflineTurnSync(queue, conv);
  });

  test('replays queued turns with their idempotency key and clears them', () async {
    await queue.enqueue(_turn('a'));
    await queue.enqueue(_turn('b'));
    when(
      () => conv.sendTurn(any(), any(), idempotencyKey: any(named: 'idempotencyKey')),
    ).thenAnswer((_) async => 'reply');

    final sent = await sync.sync();

    expect(sent, 2);
    expect(await queue.pending(), isEmpty);
    verify(() => conv.sendTurn(1, 'hi', idempotencyKey: 'a')).called(1);
    verify(() => conv.sendTurn(1, 'hi', idempotencyKey: 'b')).called(1);
  });

  test('a network error stops the run and keeps the rest queued', () async {
    await queue.enqueue(_turn('a'));
    await queue.enqueue(_turn('b'));
    when(
      () => conv.sendTurn(1, 'hi', idempotencyKey: 'a'),
    ).thenThrow(const ApiException(statusCode: 0, code: 'network', message: 'offline'));

    final sent = await sync.sync();

    expect(sent, 0);
    // Both remain — 'a' failed (network), 'b' never attempted.
    expect((await queue.pending()).map((t) => t.idempotencyKey), ['a', 'b']);
  });

  test('a definitive server error drops that turn and continues', () async {
    await queue.enqueue(_turn('a'));
    await queue.enqueue(_turn('b'));
    when(
      () => conv.sendTurn(1, 'hi', idempotencyKey: 'a'),
    ).thenThrow(const ApiException(statusCode: 409, code: 'conflict', message: 'ended'));
    when(
      () => conv.sendTurn(1, 'hi', idempotencyKey: 'b'),
    ).thenAnswer((_) async => 'reply');

    final sent = await sync.sync();

    expect(sent, 1); // 'b' sent; 'a' dropped (not retried forever)
    expect(await queue.pending(), isEmpty);
  });
}

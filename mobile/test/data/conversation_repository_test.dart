import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/conversation_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  late _MockApiClient api;
  late ConversationRepository repo;

  setUp(() {
    api = _MockApiClient();
    repo = ConversationRepository(api);
  });

  test('startSession posts and returns the session id', () async {
    when(
      () => api.postJson('/sessions/start', body: any(named: 'body')),
    ).thenAnswer(
      (_) async => {
        'session_id': 5,
        'room_name': 'r',
        'livekit_token': 't',
        'livekit_url': 'u',
      },
    );

    expect(await repo.startSession(), 5);
  });

  test('sendTurn posts to the turn endpoint and returns the reply', () async {
    when(
      () => api.postJson('/sessions/5/turn', body: any(named: 'body')),
    ).thenAnswer((_) async => {'reply': 'Nice!'});

    expect(await repo.sendTurn(5, 'hello'), 'Nice!');
  });

  test('endSession posts to the end endpoint', () async {
    when(() => api.postJson('/sessions/5/end')).thenAnswer((_) async => {});

    await repo.endSession(5);

    verify(() => api.postJson('/sessions/5/end')).called(1);
  });

  test('getActiveSession returns the session with its transcript', () async {
    when(() => api.getJson('/sessions/active')).thenAnswer(
      (_) async => {
        'session_id': 7,
        'mode': 'scenario',
        'scenario_id': 'restaurant',
        'turns': [
          {'role': 'user', 'content': 'hi'},
          {'role': 'assistant', 'content': 'Hello!'},
        ],
      },
    );

    final active = await repo.getActiveSession();

    expect(active!.sessionId, 7);
    expect(active.mode, 'scenario');
    expect(active.scenarioId, 'restaurant');
    expect(active.turns.map((t) => t.content).toList(), ['hi', 'Hello!']);
  });

  test('getActiveSession returns null when none is active (404)', () async {
    when(() => api.getJson('/sessions/active')).thenThrow(
      const ApiException(
        statusCode: 404,
        code: 'NotFoundError',
        message: 'No active session',
      ),
    );

    expect(await repo.getActiveSession(), isNull);
  });
}

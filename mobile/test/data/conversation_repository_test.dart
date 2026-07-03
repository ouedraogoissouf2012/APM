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
}

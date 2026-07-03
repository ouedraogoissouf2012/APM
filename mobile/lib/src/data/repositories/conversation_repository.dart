import '../../core/network/authenticated_api_client.dart';

/// Talks to the backend conversation endpoints (auth required).
class ConversationRepository {
  ConversationRepository(this._api);

  final AuthenticatedApiClient _api;

  Future<int> startSession({String mode = 'free', String? scenarioId}) async {
    final json = await _api.postJson(
      '/sessions/start',
      body: {'mode': mode, 'scenario_id': ?scenarioId},
    );
    return json['session_id'] as int;
  }

  Future<String> sendTurn(int sessionId, String text) async {
    final json = await _api.postJson(
      '/sessions/$sessionId/turn',
      body: {'text': text},
    );
    return json['reply'] as String;
  }

  Future<void> endSession(int sessionId) async {
    await _api.postJson('/sessions/$sessionId/end');
  }
}

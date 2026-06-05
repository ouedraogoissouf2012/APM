import '../../core/network/api_client.dart';
import '../../core/storage/token_storage.dart';

/// Talks to the backend conversation endpoints (auth required).
class ConversationRepository {
  ConversationRepository(this._api, this._storage);

  final ApiClient _api;
  final TokenStorage _storage;

  Future<int> startSession({String mode = 'free', String? scenarioId}) async {
    final json = await _api.postJson(
      '/sessions/start',
      body: {
        'mode': mode,
        'scenario_id': ?scenarioId,
      },
      bearer: await _storage.readAccessToken(),
    );
    return json['session_id'] as int;
  }

  Future<String> sendTurn(int sessionId, String text) async {
    final json = await _api.postJson(
      '/sessions/$sessionId/turn',
      body: {'text': text},
      bearer: await _storage.readAccessToken(),
    );
    return json['reply'] as String;
  }

  Future<void> endSession(int sessionId) async {
    await _api.postJson(
      '/sessions/$sessionId/end',
      bearer: await _storage.readAccessToken(),
    );
  }
}

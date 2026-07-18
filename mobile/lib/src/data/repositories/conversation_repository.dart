import '../../core/network/api_exception.dart';
import '../../core/network/authenticated_api_client.dart';

/// The user's in-progress session plus its transcript so far, used to resume a
/// conversation the app lost track of instead of dead-ending on a 409.
class ActiveSessionData {
  const ActiveSessionData({
    required this.sessionId,
    required this.mode,
    required this.scenarioId,
    required this.turns,
  });

  final int sessionId;
  final String mode;
  final String? scenarioId;
  final List<({String role, String content})> turns;
}

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

  /// Returns the in-progress session (with its transcript), or null if none.
  Future<ActiveSessionData?> getActiveSession() async {
    try {
      final json = await _api.getJson('/sessions/active');
      final rawTurns = json['turns'] as List<dynamic>? ?? const [];
      return ActiveSessionData(
        sessionId: json['session_id'] as int,
        mode: json['mode'] as String,
        scenarioId: json['scenario_id'] as String?,
        turns: [
          for (final t in rawTurns)
            (
              role: (t as Map)['role'] as String,
              content: t['content'] as String,
            ),
        ],
      );
    } on ApiException catch (e) {
      if (e.statusCode == 404) return null;
      rethrow;
    }
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

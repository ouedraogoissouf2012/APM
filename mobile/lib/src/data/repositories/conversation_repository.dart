import '../../core/network/api_exception.dart';
import '../../core/network/authenticated_api_client.dart';
import '../../core/network/sse.dart';

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

  /// Streams the reply one sentence at a time via Server-Sent Events, so the
  /// caller can speak each sentence as soon as it arrives instead of waiting
  /// for the whole reply. Throws if the server emits an `error` event.
  Stream<String> streamTurn(int sessionId, String text) async* {
    final lines = _api.postLineStream(
      '/sessions/$sessionId/turn/stream',
      body: {'text': text},
    );
    await for (final event in parseSse(lines)) {
      switch (event.event) {
        case 'chunk':
          final text = sseChunkText(event.data);
          if (text != null && text.isNotEmpty) yield text;
        case 'error':
          throw const ApiException(
            statusCode: 502,
            code: 'LlmProviderError',
            message: 'The assistant could not reply',
          );
        case 'done':
          return;
      }
    }
  }

  Future<void> endSession(int sessionId) async {
    await _api.postJson('/sessions/$sessionId/end');
  }
}

import 'dart:convert';

import '../../core/network/api_exception.dart';
import '../../core/network/authenticated_api_client.dart';
import '../../core/network/sse.dart';
import '../models/turn_correction.dart';

/// One event from a streamed conversation turn: either a speakable sentence of
/// the reply, or (at most once, at the end) a grammar correction of what the
/// learner just said.
sealed class TurnEvent {
  const TurnEvent();
}

class ReplySentence extends TurnEvent {
  const ReplySentence(this.text);
  final String text;
}

class CorrectionEvent extends TurnEvent {
  const CorrectionEvent(this.correction);
  final TurnCorrection correction;
}

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

  /// Streams a conversation turn via Server-Sent Events: a [ReplySentence] per
  /// sentence (so the caller can speak each one as it arrives instead of waiting
  /// for the whole reply), then at most one [CorrectionEvent] for what the
  /// learner said. Throws if the server emits an `error` event.
  Stream<TurnEvent> streamTurn(int sessionId, String text) async* {
    final lines = _api.postLineStream(
      '/sessions/$sessionId/turn/stream',
      body: {'text': text},
    );
    await for (final event in parseSse(lines)) {
      switch (event.event) {
        case 'chunk':
          final text = sseChunkText(event.data);
          if (text != null && text.isNotEmpty) yield ReplySentence(text);
        case 'correction':
          final correction = _parseCorrection(event.data);
          if (correction != null) yield CorrectionEvent(correction);
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

  TurnCorrection? _parseCorrection(String data) {
    if (data.isEmpty) return null;
    try {
      final decoded = jsonDecode(data);
      if (decoded is Map<String, dynamic>) {
        return TurnCorrection.fromJson(decoded);
      }
    } catch (_) {
      // Malformed correction payload — skip it rather than break the turn.
    }
    return null;
  }

  Future<void> endSession(int sessionId) async {
    await _api.postJson('/sessions/$sessionId/end');
  }
}

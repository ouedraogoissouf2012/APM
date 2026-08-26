import '../../../data/models/turn_correction.dart';

enum ConversationStatus { idle, listening, thinking, speaking }

/// Turn roles — protocol values shared with the backend transcript.
const String kRoleUser = 'user';
const String kRoleAssistant = 'assistant';

class ConversationTurn {
  const ConversationTurn(this.role, this.content, {this.correction});

  final String role; // kRoleUser | kRoleAssistant
  final String content;

  /// Set on a user turn once the backend returns a grammar correction for it,
  /// so the UI can render the gold correction chip under the bubble.
  final TurnCorrection? correction;

  ConversationTurn withCorrection(TurnCorrection correction) =>
      ConversationTurn(role, content, correction: correction);
}

class ConversationState {
  const ConversationState({
    this.sessionId,
    this.scenarioId,
    this.turns = const [],
    this.status = ConversationStatus.idle,
    this.error,
    this.partialTranscript,
    this.quotaExhausted = false,
    this.sessionConflict = false,
  });

  final int? sessionId;

  /// The skill this session practises (scenario mode). null for free/mission.
  /// Used to key the learner's spoken takes for the audible before/after (#199).
  final String? scenarioId;

  final List<ConversationTurn> turns;
  final ConversationStatus status;
  final String? error;

  /// Interim recognized words shown live while the learner speaks; null when
  /// not listening or nothing has been heard yet.
  final String? partialTranscript;

  /// True when the session could not start because the daily free quota is
  /// spent. A distinct state (not a plain error) so the UI can offer an
  /// upgrade path rather than a dead conversation screen.
  final bool quotaExhausted;

  /// True when a target-less start hit 409: an active session exists and the
  /// learner must choose resume vs replace. Distinct from a plain error so the
  /// UI can show a choice screen rather than the orb.
  final bool sessionConflict;

  bool get isActive => sessionId != null;

  ConversationState copyWith({
    int? sessionId,
    String? scenarioId,
    List<ConversationTurn>? turns,
    ConversationStatus? status,
    String? error,
    String? partialTranscript,
    bool? quotaExhausted,
    bool? sessionConflict,
    bool clearError = false,
    bool clearPartial = false,
  }) {
    return ConversationState(
      sessionId: sessionId ?? this.sessionId,
      scenarioId: scenarioId ?? this.scenarioId,
      turns: turns ?? this.turns,
      status: status ?? this.status,
      error: clearError ? null : (error ?? this.error),
      partialTranscript:
          clearPartial ? null : (partialTranscript ?? this.partialTranscript),
      quotaExhausted: quotaExhausted ?? this.quotaExhausted,
      sessionConflict: sessionConflict ?? this.sessionConflict,
    );
  }
}

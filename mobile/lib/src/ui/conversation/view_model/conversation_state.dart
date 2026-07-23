enum ConversationStatus { idle, listening, thinking, speaking }

/// Turn roles — protocol values shared with the backend transcript.
const String kRoleUser = 'user';
const String kRoleAssistant = 'assistant';

class ConversationTurn {
  const ConversationTurn(this.role, this.content);

  final String role; // kRoleUser | kRoleAssistant
  final String content;
}

class ConversationState {
  const ConversationState({
    this.sessionId,
    this.turns = const [],
    this.status = ConversationStatus.idle,
    this.error,
    this.partialTranscript,
    this.quotaExhausted = false,
  });

  final int? sessionId;
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

  bool get isActive => sessionId != null;

  ConversationState copyWith({
    int? sessionId,
    List<ConversationTurn>? turns,
    ConversationStatus? status,
    String? error,
    String? partialTranscript,
    bool? quotaExhausted,
    bool clearError = false,
    bool clearPartial = false,
  }) {
    return ConversationState(
      sessionId: sessionId ?? this.sessionId,
      turns: turns ?? this.turns,
      status: status ?? this.status,
      error: clearError ? null : (error ?? this.error),
      partialTranscript:
          clearPartial ? null : (partialTranscript ?? this.partialTranscript),
      quotaExhausted: quotaExhausted ?? this.quotaExhausted,
    );
  }
}

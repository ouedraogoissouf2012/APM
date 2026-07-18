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
  });

  final int? sessionId;
  final List<ConversationTurn> turns;
  final ConversationStatus status;
  final String? error;

  bool get isActive => sessionId != null;

  ConversationState copyWith({
    int? sessionId,
    List<ConversationTurn>? turns,
    ConversationStatus? status,
    String? error,
    bool clearError = false,
  }) {
    return ConversationState(
      sessionId: sessionId ?? this.sessionId,
      turns: turns ?? this.turns,
      status: status ?? this.status,
      error: clearError ? null : (error ?? this.error),
    );
  }
}

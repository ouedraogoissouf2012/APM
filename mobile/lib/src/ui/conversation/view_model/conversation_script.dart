import '../../../data/models/scenarios.dart';
import '../../../data/models/session_modes.dart';

/// Pure conversation copy (what the AI says to open a session). Product logic,
/// deliberately separate from the ViewModel's orchestration so it can evolve
/// and be tested in isolation. No state, no I/O.
abstract final class ConversationScript {
  /// The assistant's first line. Names the scenario for guided sessions,
  /// otherwise invites an open topic. Reuses [scenarioTitle] so the scenario
  /// wording stays consistent with the rest of the app (single source).
  static String openingMessage({
    required String mode,
    required String? scenarioId,
  }) {
    if (mode == kSessionModeScenario && scenarioId != null) {
      final title = scenarioTitle(scenarioId).toLowerCase();
      return "Let's practise $title. "
          'I will keep it simple and ask you questions.';
    }
    return "Hi, let's practise English. "
        'What would you like to talk about today?';
  }
}

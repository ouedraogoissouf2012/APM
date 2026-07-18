import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/network/providers.dart';
import '../../../core/speech/speech_service.dart';
import '../../../data/models/session_modes.dart';
import '../../../data/repositories/conversation_repository.dart';
import '../../profile/view_model/profile_view_model.dart';
import 'conversation_state.dart';

/// A single long-lived speech service. It must NEVER be rebuilt: the
/// underlying speech_to_text plugin is a process singleton that binds its
/// status callback to the first instance — a second instance would hang
/// forever. Accent changes go through setLanguage() in [ConversationViewModel.start].
final speechServiceProvider = Provider<SpeechService>(
  (ref) => DeviceSpeechService(),
);

final conversationRepositoryProvider = Provider<ConversationRepository>(
  (ref) => ConversationRepository(ref.watch(authenticatedApiClientProvider)),
);

final conversationViewModelProvider =
    NotifierProvider<ConversationViewModel, ConversationState>(
      ConversationViewModel.new,
    );

/// Drives one turn at a time: listen (device STT) -> send to backend (DeepSeek)
/// -> speak the reply (device TTS). Turn-based, no real-time audio streaming.
class ConversationViewModel extends Notifier<ConversationState> {
  @override
  ConversationState build() => const ConversationState();

  Future<void> start({
    String mode = kSessionModeFree,
    String? scenarioId,
  }) async {
    final repo = ref.read(conversationRepositoryProvider);

    int sessionId;
    List<ConversationTurn> turns;
    try {
      sessionId = await repo.startSession(mode: mode, scenarioId: scenarioId);
      turns = [
        ConversationTurn(kRoleAssistant, _openingMessage(mode, scenarioId)),
      ];
    } on ApiException catch (e) {
      // A session is already in progress (409): resume it instead of leaving
      // the user stuck. The backend allows only one active session per user.
      if (e.statusCode != 409) rethrow;
      final active = await repo.getActiveSession();
      if (active == null) rethrow;
      sessionId = active.sessionId;
      turns = active.turns.isEmpty
          ? [
              ConversationTurn(
                kRoleAssistant,
                _openingMessage(active.mode, active.scenarioId),
              ),
            ]
          : [
              for (final t in active.turns) ConversationTurn(t.role, t.content),
            ];
    }

    final speech = ref.read(speechServiceProvider);
    await speech.setLanguage(await _preferredLanguageTag());
    final speechReady = await speech.initialize();
    if (!ref.mounted) return;
    state = ConversationState(
      sessionId: sessionId,
      turns: turns,
      error: speechReady ? null : 'Microphone is not available',
    );
  }

  /// The learner's practice locale from their profile accent ('us' | 'uk').
  /// Bounded wait: Riverpod retries failing providers, so an unavailable
  /// profile must not block the conversation — fall back to US English.
  Future<String> _preferredLanguageTag() async {
    final accent = ref.read(profileViewModelProvider).value?.accent;
    if (accent != null) return languageTagForAccent(accent);
    try {
      final profile = await ref
          .read(profileViewModelProvider.future)
          .timeout(const Duration(seconds: 3));
      return languageTagForAccent(profile.accent);
    } catch (_) {
      return languageTagForAccent(null);
    }
  }

  Future<void> listenAndRespond() async {
    final sessionId = state.sessionId;
    if (sessionId == null || state.status != ConversationStatus.idle) return;

    state = state.copyWith(
      status: ConversationStatus.listening,
      clearError: true,
    );
    final speech = ref.read(speechServiceProvider);
    final text = (await speech.listenOnce()).trim();
    if (text.isEmpty) {
      state = state.copyWith(status: ConversationStatus.idle);
      return;
    }

    state = state.copyWith(
      turns: [...state.turns, ConversationTurn(kRoleUser, text)],
      status: ConversationStatus.thinking,
    );

    try {
      final reply = await ref
          .read(conversationRepositoryProvider)
          .sendTurn(sessionId, text);
      state = state.copyWith(
        turns: [...state.turns, ConversationTurn(kRoleAssistant, reply)],
        status: ConversationStatus.speaking,
      );
      await speech.speak(reply);
      state = state.copyWith(status: ConversationStatus.idle);
    } catch (_) {
      state = state.copyWith(
        status: ConversationStatus.idle,
        error: 'Could not get a reply',
      );
    }
  }

  Future<void> end() async {
    final id = state.sessionId;
    if (id != null) {
      await ref.read(conversationRepositoryProvider).endSession(id);
    }
    state = const ConversationState();
  }
}

String _openingMessage(String mode, String? scenarioId) {
  if (mode == kSessionModeScenario && scenarioId != null) {
    final scenario = scenarioId.replaceAll('_', ' ');
    return "Let's practise $scenario. I will keep it simple and ask you questions.";
  }
  return "Hi, let's practise English. What would you like to talk about today?";
}

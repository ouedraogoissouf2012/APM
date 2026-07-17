import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/speech/speech_service.dart';
import '../../../data/repositories/conversation_repository.dart';
import '../../auth/view_model/auth_view_model.dart';
import 'conversation_state.dart';

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

  Future<void> start({String mode = 'free', String? scenarioId}) async {
    final repo = ref.read(conversationRepositoryProvider);

    int sessionId;
    List<ConversationTurn> turns;
    try {
      sessionId = await repo.startSession(mode: mode, scenarioId: scenarioId);
      turns = [ConversationTurn('assistant', _openingMessage(mode, scenarioId))];
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
                'assistant',
                _openingMessage(active.mode, active.scenarioId),
              ),
            ]
          : [
              for (final t in active.turns) ConversationTurn(t.role, t.content),
            ];
    }

    final speechReady = await ref.read(speechServiceProvider).initialize();
    state = ConversationState(
      sessionId: sessionId,
      turns: turns,
      error: speechReady ? null : 'Microphone is not available',
    );
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
      turns: [...state.turns, ConversationTurn('user', text)],
      status: ConversationStatus.thinking,
    );

    try {
      final reply = await ref
          .read(conversationRepositoryProvider)
          .sendTurn(sessionId, text);
      state = state.copyWith(
        turns: [...state.turns, ConversationTurn('assistant', reply)],
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
  if (mode == 'scenario' && scenarioId != null) {
    final scenario = scenarioId.replaceAll('_', ' ');
    return "Let's practise $scenario. I will keep it simple and ask you questions.";
  }
  return "Hi, let's practise English. What would you like to talk about today?";
}

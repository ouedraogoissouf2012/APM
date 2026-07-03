import 'package:flutter_riverpod/flutter_riverpod.dart';

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
    final id = await ref
        .read(conversationRepositoryProvider)
        .startSession(mode: mode, scenarioId: scenarioId);
    final speechReady = await ref.read(speechServiceProvider).initialize();
    state = ConversationState(
      sessionId: id,
      turns: [ConversationTurn('assistant', _openingMessage(mode, scenarioId))],
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

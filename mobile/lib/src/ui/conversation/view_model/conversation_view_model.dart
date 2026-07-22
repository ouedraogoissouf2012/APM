import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/network/providers.dart';
import '../../../core/speech/speech_service.dart';
import '../../../data/models/session_modes.dart';
import '../../../data/repositories/conversation_repository.dart';
import '../../profile/view_model/profile_view_model.dart';
import 'conversation_script.dart';
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
        ConversationTurn(
          kRoleAssistant,
          ConversationScript.openingMessage(mode: mode, scenarioId: scenarioId),
        ),
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
                ConversationScript.openingMessage(
                  mode: active.mode,
                  scenarioId: active.scenarioId,
                ),
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

  /// True while a hands-free conversation loop is running. Cleared by
  /// [stopConversation]/[end] to break the loop after the in-flight turn.
  bool _conversing = false;

  /// The loop and every turn step are still "live" only while the loop is
  /// running and the notifier is mounted. This single predicate replaces the
  /// checks that used to be duplicated after each `await`, so a step can never
  /// mutate state on behalf of a loop that was already stopped or disposed.
  bool get _active => _conversing && ref.mounted;

  /// Starts a hands-free conversation loop: listen → send → speak → listen…
  /// One tap begins it; it continues automatically until the learner falls
  /// silent (empty transcript), an error occurs, or it is explicitly stopped.
  Future<void> listenAndRespond() async {
    if (state.sessionId == null || state.status != ConversationStatus.idle) {
      return;
    }
    if (_conversing) return;
    _conversing = true;
    try {
      while (_active && await _runOneTurn()) {}
    } finally {
      _conversing = false;
      // Settle back to idle only if a session is still live: end() may have
      // reset the state entirely, and _fetchReply may have set an error we
      // must not clobber. Guarding on an active, non-error session keeps this
      // a no-op in those cases.
      if (ref.mounted &&
          state.sessionId != null &&
          state.status != ConversationStatus.idle) {
        state = state.copyWith(status: ConversationStatus.idle);
      }
    }
  }

  /// One listen → respond → speak turn. Returns whether the loop should carry
  /// on (learner spoke and got a reply) or stop (silence, error, or stopped).
  /// Each phase is guarded by [_active]: a turn resolving after the loop was
  /// stopped simply bails without touching state.
  Future<bool> _runOneTurn() async {
    final sessionId = state.sessionId;
    if (sessionId == null) return false;

    final heard = await _listen();
    if (!_active || heard.isEmpty) return false;
    _appendTurn(kRoleUser, ConversationStatus.thinking, heard);

    final reply = await _fetchReply(sessionId, heard);
    if (reply == null) return false; // error already surfaced
    if (!_active) return false;
    _appendTurn(kRoleAssistant, ConversationStatus.speaking, reply);

    await ref.read(speechServiceProvider).speak(reply);
    return _active;
  }

  /// Listens for one utterance, streaming partial words to the UI.
  Future<String> _listen() async {
    state = state.copyWith(
      status: ConversationStatus.listening,
      clearError: true,
      clearPartial: true,
    );
    final text = await ref.read(speechServiceProvider).listenOnce(
          onPartial: _onPartial,
        );
    return text.trim();
  }

  /// Sends the learner's line to the backend. Returns the reply, or null after
  /// surfacing a user-facing error (which also ends the loop).
  Future<String?> _fetchReply(int sessionId, String text) async {
    try {
      return await ref
          .read(conversationRepositoryProvider)
          .sendTurn(sessionId, text);
    } catch (_) {
      if (ref.mounted) {
        state = state.copyWith(
          status: ConversationStatus.idle,
          error: 'Could not get a reply',
        );
      }
      return null;
    }
  }

  /// Appends a turn and moves to [next]. Single place that grows the transcript.
  void _appendTurn(String role, ConversationStatus next, String content) {
    state = state.copyWith(
      turns: [...state.turns, ConversationTurn(role, content)],
      status: next,
    );
  }

  /// Live partial transcript, shown on screen while the learner is speaking.
  void _onPartial(String words) {
    if (state.status == ConversationStatus.listening) {
      state = state.copyWith(partialTranscript: words);
    }
  }

  /// Stops the loop and the recognizer, returning to idle.
  Future<void> stopConversation() async {
    _conversing = false;
    await ref.read(speechServiceProvider).stopListening();
    if (ref.mounted && state.sessionId != null) {
      state = state.copyWith(
        status: ConversationStatus.idle,
        clearPartial: true,
      );
    }
  }

  Future<void> end() async {
    _conversing = false;
    await ref.read(speechServiceProvider).stopListening();
    final id = state.sessionId;
    if (id != null) {
      await ref.read(conversationRepositoryProvider).endSession(id);
    }
    state = const ConversationState();
  }
}

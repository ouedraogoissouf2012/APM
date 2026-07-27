import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/audio_playback_service.dart';
import '../../../core/audio/audio_recording_service.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/providers.dart';
import '../../../core/speech/speech_service.dart';
import '../../../data/models/session_modes.dart';
import '../../../data/models/turn_correction.dart';
import '../../../data/repositories/conversation_repository.dart';
import '../../profile/view_model/profile_view_model.dart';
import 'conversation_script.dart';
import 'conversation_state.dart';
import 'speech_error_message.dart';

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

final audioPlaybackProvider = Provider<AudioPlaybackService>(
  (ref) => DeviceAudioPlaybackService(),
);

final audioRecordingProvider = Provider<AudioRecordingService>(
  (ref) => DeviceAudioRecordingService(),
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
      // Daily free quota spent (402): surface a friendly paywall state rather
      // than letting the exception reach the UI as an uncaught error.
      if (e.statusCode == 402) {
        if (ref.mounted) {
          state = const ConversationState(quotaExhausted: true);
        }
        return;
      }
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

  /// Intent flag: true while the learner wants the hands-free loop to continue.
  /// Cleared by [stopConversation]/[end] to end the loop after the in-flight
  /// turn resolves.
  bool _conversing = false;

  /// Re-entrancy guard held for the WHOLE lifetime of [listenAndRespond],
  /// released only in its `finally`. [_conversing] is insufficient on its own:
  /// stopConversation() clears it while its own `await stopListening()` is
  /// still pending, so a fast stop→re-tap could otherwise start a second loop
  /// before the first has unwound — two recognizers, the "already started"
  /// crash. This guard makes a concurrent loop impossible by construction.
  bool _loopRunning = false;

  /// The loop and every turn step are still "live" only while the loop is
  /// wanted and the notifier is mounted. This single predicate replaces the
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
    // Server STT (Whisper via Groq): push-to-talk. This tap starts recording;
    // the next tap stops, transcribes and responds. No hands-free auto-loop,
    // because accurate transcription needs a clean full recording.
    if (await ref.read(serverSttProvider.future)) {
      await _startRecording();
      return;
    }
    if (_loopRunning) return; // a prior loop is still unwinding
    _loopRunning = true;
    _conversing = true;
    try {
      while (_active && await _runOneTurn()) {}
    } finally {
      _conversing = false;
      _loopRunning = false;
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
    if (!_active) return false;
    if (heard.isEmpty) {
      _surfaceListenError(); // no-op on plain silence, message on failure
      return false;
    }
    _appendTurn(kRoleUser, ConversationStatus.thinking, heard);
    return _streamReplyAndSpeak(sessionId, heard);
  }

  /// Streams the reply sentence by sentence: each sentence is spoken as soon as
  /// it arrives (so the learner hears the first words while the model is still
  /// writing) and the on-screen reply grows in step. This is what removes the
  /// long silence before the assistant starts talking.
  Future<bool> _streamReplyAndSpeak(int sessionId, String heard) async {
    final speech = ref.read(speechServiceProvider);
    final audio = ref.read(audioPlaybackProvider);
    // Server-side neural voice? Then the reply arrives as audio clips to play;
    // otherwise fall back to the on-device system voice. Defaults to false
    // (on-device) if the backend/config is unreachable.
    final serverTts = await ref.read(serverTtsProvider.future);
    final buffer = StringBuffer();
    var hasText = false;
    try {
      final events = ref
          .read(conversationRepositoryProvider)
          .streamTurn(sessionId, heard);
      await for (final event in events) {
        if (!_active) return false;
        switch (event) {
          case ReplySentence(:final text):
            buffer.write(hasText ? ' $text' : text);
            _setAssistantReply(buffer.toString());
            hasText = true;
            // Only speak on-device when the backend is NOT sending audio.
            if (!serverTts) await speech.speak(text);
          case AudioClip(:final audioB64, :final mime):
            // Real neural voice: play it (awaits until the clip finishes).
            await audio.playClip(audioB64, mime);
          case CorrectionEvent(:final correction):
            // Attach to the learner's turn -> gold chip under their bubble.
            _attachCorrection(correction);
        }
        if (!_active) return false;
      }
    } catch (_) {
      if (ref.mounted) {
        state = state.copyWith(
          status: ConversationStatus.idle,
          error: 'Could not get a reply',
        );
      }
      return false;
    }
    return _active;
  }

  /// Attaches a grammar correction to the learner's most recent user turn, so
  /// the UI renders the gold correction chip under that bubble.
  void _attachCorrection(TurnCorrection correction) {
    final turns = [...state.turns];
    for (var i = turns.length - 1; i >= 0; i--) {
      if (turns[i].role == kRoleUser) {
        turns[i] = turns[i].withCorrection(correction);
        state = state.copyWith(turns: turns);
        return;
      }
    }
  }

  /// Sets (or replaces) the current assistant turn as its text streams in, and
  /// moves to the speaking state. Replaces the last assistant turn in place so
  /// the transcript shows one growing reply, not a sentence per turn.
  void _setAssistantReply(String content) {
    final turns = [...state.turns];
    if (turns.isNotEmpty && turns.last.role == kRoleAssistant) {
      turns[turns.length - 1] = ConversationTurn(kRoleAssistant, content);
    } else {
      turns.add(ConversationTurn(kRoleAssistant, content));
    }
    state = state.copyWith(
      turns: turns,
      status: ConversationStatus.speaking,
    );
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

  /// After an empty utterance, show a helpful message only if the recognizer
  /// actually failed. Plain silence (learner said nothing) is not an error and
  /// leaves the state clean.
  void _surfaceListenError() {
    final message = speechErrorMessage(ref.read(speechServiceProvider).lastError);
    state = state.copyWith(
      status: ConversationStatus.idle,
      error: message,
      clearError: message == null,
    );
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

  /// Push-to-talk: true while recording the learner's utterance (server STT).
  bool _recording = false;

  /// Starts recording the learner's voice (server STT / push-to-talk).
  Future<void> _startRecording() async {
    final started = await ref.read(audioRecordingProvider).start();
    if (!ref.mounted) return;
    if (!started) {
      state = state.copyWith(error: 'Microphone is not available');
      return;
    }
    _recording = true;
    state = state.copyWith(
      status: ConversationStatus.listening,
      clearError: true,
      clearPartial: true,
    );
  }

  /// Stops recording, transcribes the audio server-side, then responds.
  Future<void> _stopRecordingAndRespond() async {
    _recording = false;
    final sessionId = state.sessionId;
    final bytes = await ref.read(audioRecordingProvider).stop();
    if (!ref.mounted || sessionId == null) return;
    if (bytes == null || bytes.isEmpty) {
      state = state.copyWith(status: ConversationStatus.idle);
      return;
    }
    state = state.copyWith(status: ConversationStatus.thinking, clearPartial: true);
    final String heard;
    try {
      heard = (await ref
              .read(conversationRepositoryProvider)
              .transcribe(bytes))
          .trim();
    } catch (_) {
      if (ref.mounted) {
        state = state.copyWith(
          status: ConversationStatus.idle,
          error: 'Could not understand you — try again',
        );
      }
      return;
    }
    if (!ref.mounted) return;
    if (heard.isEmpty) {
      state = state.copyWith(status: ConversationStatus.idle);
      return;
    }
    _appendTurn(kRoleUser, ConversationStatus.thinking, heard);
    // Reuse the reply flow, which guards on `_active` (= _conversing); enable it
    // for the duration of this single response.
    _conversing = true;
    try {
      await _streamReplyAndSpeak(sessionId, heard);
    } finally {
      _conversing = false;
      if (ref.mounted &&
          state.sessionId != null &&
          state.status != ConversationStatus.idle) {
        state = state.copyWith(status: ConversationStatus.idle);
      }
    }
  }

  /// Stops the loop / the recording, returning to idle. In push-to-talk mode a
  /// tap while recording ends the utterance and triggers the response.
  Future<void> stopConversation() async {
    if (_recording) {
      await _stopRecordingAndRespond();
      return;
    }
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
    if (_recording) {
      _recording = false;
      await ref.read(audioRecordingProvider).cancel();
    }
    await ref.read(speechServiceProvider).stopListening();
    final id = state.sessionId;
    if (id != null) {
      await ref.read(conversationRepositoryProvider).endSession(id);
    }
    state = const ConversationState();
  }
}

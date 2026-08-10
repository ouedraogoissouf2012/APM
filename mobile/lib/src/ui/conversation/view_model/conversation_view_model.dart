import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/network/providers.dart';
import '../../../core/speech/speech_service.dart';
import '../../../data/models/session_modes.dart';
import '../../history/view_model/progress_view_model.dart';
import '../../home/view_model/streak_view_model.dart';
import '../../profile/view_model/profile_view_model.dart';
import '../../review/view_model/review_view_model.dart';
import 'conversation_host.dart';
import 'conversation_providers.dart';
import 'conversation_script.dart';
import 'conversation_state.dart';
import 'push_to_talk_controller.dart';
import 'reply_playback.dart';
import 'turn_loop_controller.dart';

// speechServiceProvider and conversationRepositoryProvider now live in
// conversation_providers.dart, re-exported here so existing importers keep working.
export 'conversation_providers.dart' show conversationRepositoryProvider, speechServiceProvider;

final conversationViewModelProvider = NotifierProvider<ConversationViewModel, ConversationState>(
  ConversationViewModel.new,
);

/// Drives one turn at a time: listen (device or server STT) -> send to the
/// backend -> voice the reply, which streams back sentence by sentence as text
/// (spoken on-device) or as neural audio clips (server TTS), played in order.
///
/// Orchestrates the extracted pieces (#121): [ReplyPlayback] consumes the reply
/// stream for both input modes. It implements [ConversationHost] so those pieces
/// read/write the shared state through a narrow seam rather than the Notifier.
class ConversationViewModel extends Notifier<ConversationState> implements ConversationHost {
  @override
  ConversationState build() => const ConversationState();

  late final ReplyPlayback _playback = ReplyPlayback(ref, this);
  late final PushToTalkController _pushToTalk = PushToTalkController(ref, this, _playback);
  late final TurnLoopController _loop = TurnLoopController(ref, this, _playback);

  // ConversationHost: the seam the extracted controllers use.
  @override
  bool get mounted => ref.mounted;

  Future<void> start({String mode = kSessionModeFree, String? scenarioId, int? missionId}) async {
    final repo = ref.read(conversationRepositoryProvider);

    int sessionId;
    List<ConversationTurn> turns;
    // The skill actually being practised (for the audible-take capture, #199):
    // the requested scenario normally, or the resumed session's scenario on a
    // target-less 409 resume.
    String? effectiveScenarioId = scenarioId;
    try {
      sessionId = await repo.startSession(mode: mode, scenarioId: scenarioId, missionId: missionId);
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
      // A session is already in progress (409): only one active session per user.
      if (e.statusCode != 409) rethrow;
      final active = await repo.getActiveSession();
      if (active == null) rethrow;
      // If the learner asked for a SPECIFIC target (a mission or scenario), do NOT
      // silently resume an unrelated active session — that swallows the mission
      // they just launched and dumps them back in an old chat. End the active one
      // and start the requested target. Only a target-less "just talk" resumes.
      final wantsSpecificTarget = missionId != null || scenarioId != null;
      if (wantsSpecificTarget) {
        await repo.endSession(active.sessionId);
        sessionId = await repo.startSession(
          mode: mode,
          scenarioId: scenarioId,
          missionId: missionId,
        );
        turns = [
          ConversationTurn(
            kRoleAssistant,
            ConversationScript.openingMessage(mode: mode, scenarioId: scenarioId),
          ),
        ];
      } else {
        sessionId = active.sessionId;
        effectiveScenarioId = active.scenarioId;
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
            : [for (final t in active.turns) ConversationTurn(t.role, t.content)];
      }
    }

    final speech = ref.read(speechServiceProvider);
    await speech.setLanguage(await _preferredLanguageTag());
    final speechReady = await speech.initialize();
    if (!ref.mounted) return;
    state = ConversationState(
      sessionId: sessionId,
      scenarioId: effectiveScenarioId,
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

  /// One tap: push-to-talk (server STT) records; otherwise start the hands-free
  /// device-STT loop. Both no-op unless a session is idle and ready.
  Future<void> listenAndRespond() async {
    if (state.sessionId == null || state.status != ConversationStatus.idle) {
      return;
    }
    // Server STT (Whisper via Groq): push-to-talk. This tap starts recording;
    // the next tap stops, transcribes and responds. No hands-free auto-loop,
    // because accurate transcription needs a clean full recording. The user's
    // transcription consent is honored: revoking it forces on-device STT.
    if (await ref.read(effectiveServerSttProvider.future)) {
      await _pushToTalk.startRecording();
      return;
    }
    await _loop.run();
  }

  /// Stops the loop / the recording, returning to idle. In push-to-talk mode a
  /// tap while recording ends the utterance and triggers the response.
  Future<void> stopConversation() async {
    if (_pushToTalk.isRecording) {
      await _pushToTalk.stopAndRespond();
      return;
    }
    _loop.stop();
    await _playback.cancel();
    await ref.read(speechServiceProvider).stopListening();
    if (ref.mounted && state.sessionId != null) {
      state = state.copyWith(status: ConversationStatus.idle, clearPartial: true);
    }
  }

  /// Stops the microphone, the turn loop and any in-flight playback/recording
  /// WITHOUT ending the session server-side — used when the screen is left or the
  /// app is backgrounded (#222) so the mic and hands-free loop cannot keep running
  /// off-screen. The session stays open so the learner can resume it (a re-entry
  /// resumes via the 409 path); [end] is the deliberate "Terminer". Idempotent:
  /// safe to call when already idle or after [end] has reset the state.
  Future<void> cancel() async {
    _loop.stop(); // pure flag, no ref — always safe
    // Re-check ref.mounted before EACH ref use: this runs from the screen's
    // dispose, and the provider can be torn down during an await gap (e.g. app
    // teardown / a disposed ProviderScope), after which touching ref throws
    // UnmountedRefException. The checks are synchronous-adjacent to each call, so
    // there is no window between the guard and the ref.read.
    if (ref.mounted) await _pushToTalk.cancel();
    if (ref.mounted) await _playback.cancel();
    if (ref.mounted) await ref.read(speechServiceProvider).stopListening();
    if (ref.mounted && state.sessionId != null && state.status != ConversationStatus.idle) {
      state = state.copyWith(status: ConversationStatus.idle, clearPartial: true);
    }
  }

  Future<void> end() async {
    _loop.stop();
    await _pushToTalk.cancel();
    await _playback.cancel();
    await ref.read(speechServiceProvider).stopListening();
    final id = state.sessionId;
    if (id != null) {
      await ref.read(conversationRepositoryProvider).endSession(id);
      if (ref.mounted) {
        ref.invalidate(streakProvider);
        ref.invalidate(reviewProvider);
        ref.invalidate(progressProvider);
      }
    }
    state = const ConversationState();
  }

  /// Test hook: await any in-flight background audio playback. Production code
  /// never blocks a turn on playback (it runs in the background by design).
  @visibleForTesting
  Future<void> awaitPlaybackForTest() => _playback.awaitPlayback();
}

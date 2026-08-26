import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/network/providers.dart';
import '../../../core/observability/providers.dart';
import '../../../core/offline/connectivity_controller.dart';
import '../../../core/speech/speech_service.dart';
import '../../../data/models/session_modes.dart';
import '../../../data/repositories/conversation_repository.dart'
    show ActiveSessionData;
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
export 'conversation_providers.dart'
    show
        billingRepositoryProvider,
        conversationRepositoryProvider,
        speechServiceProvider;

final conversationViewModelProvider =
    NotifierProvider<ConversationViewModel, ConversationState>(
      ConversationViewModel.new,
    );

/// Drives one turn at a time: listen (device or server STT) -> send to the
/// backend -> voice the reply, which streams back sentence by sentence as text
/// (spoken on-device) or as neural audio clips (server TTS), played in order.
///
/// Orchestrates the extracted pieces (#121): [ReplyPlayback] consumes the reply
/// stream for both input modes. It implements [ConversationHost] so those pieces
/// read/write the shared state through a narrow seam rather than the Notifier.
class ConversationViewModel extends Notifier<ConversationState>
    implements ConversationHost {
  @override
  ConversationState build() {
    // #312: an offline turn's reply is currently thrown away by OfflineTurnSync
    // (it only returns a count) — refetch the authoritative transcript from the
    // server whenever the pending queue shrinks (a sync just replayed at least
    // one turn), so the reply that was invisible while offline actually shows
    // up. A drop can also mean a turn was definitively rejected and dropped
    // (not synced) — re-fetching is still correct either way: it shows exactly
    // what the server has, which is what the transcript should reflect.
    ref.listen<ConnectivityState>(connectivityControllerProvider, (
      previous,
      next,
    ) {
      final justSynced =
          previous != null && next.pendingCount < previous.pendingCount;
      if (justSynced) unawaited(_refreshTurnsFromServer());
    });
    return const ConversationState();
  }

  late final ReplyPlayback _playback = ReplyPlayback(ref, this);
  late final PushToTalkController _pushToTalk = PushToTalkController(
    ref,
    this,
    _playback,
  );
  late final TurnLoopController _loop = TurnLoopController(
    ref,
    this,
    _playback,
  );

  ActiveSessionData? _pendingActive;
  String _pendingMode = kSessionModeFree;
  String? _pendingScenarioId;
  int? _pendingMissionId;

  // ConversationHost: the seam the extracted controllers use.
  @override
  bool get mounted => ref.mounted;

  Future<void> start({
    String mode = kSessionModeFree,
    String? scenarioId,
    int? missionId,
  }) async {
    // #311: without this, the pending-turn counter starts at 0 on every app
    // launch regardless of what's actually queued — a turn recorded offline in
    // a previous run stays invisible (no banner, no retry) until SOMETHING else
    // happens to touch the connectivity state.
    await ref.read(connectivityControllerProvider.notifier).refresh();

    final repo = ref.read(conversationRepositoryProvider);

    int sessionId;
    List<ConversationTurn> turns;
    // The skill actually being practised (for the audible-take capture, #199):
    // the requested scenario normally, or the resumed session's scenario on a
    // target-less 409 resume.
    String? effectiveScenarioId = scenarioId;
    try {
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
      if (e.statusCode != 409) {
        // #437: a 500/network must not stay an uncaught async error — the
        // orb would sit on "préparation" with no message.
        _failStart(e.message, e);
        return;
      }
      // A throw inside `on ApiException` is NOT caught by the sibling catch
      // (#audit7 P2-03). Keep the 409 resume path inside its own try.
      try {
        final active = await repo.getActiveSession();
        if (active == null) {
          _failStart(e.message, e);
          return;
        }
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
              ConversationScript.openingMessage(
                mode: mode,
                scenarioId: scenarioId,
              ),
            ),
          ];
        } else {
          _pendingActive = active;
          _pendingMode = mode;
          _pendingScenarioId = scenarioId;
          _pendingMissionId = missionId;
          if (ref.mounted) {
            state = const ConversationState(sessionConflict: true);
          }
          return;
        }
      } catch (inner, s) {
        _failStart(
          inner is ApiException
              ? inner.message
              : 'Impossible de démarrer la session',
          inner,
          s,
        );
        return;
      }
    } catch (e, s) {
      _failStart('Impossible de démarrer la session', e, s);
      return;
    }

    await _activateSession(
      sessionId: sessionId,
      scenarioId: effectiveScenarioId,
      turns: turns,
    );
  }

  /// Reprendre: apply the 409 pending session and start speech.
  Future<void> resumePending() async {
    final active = _pendingActive;
    if (active == null) return;
    _pendingActive = null;
    final turns = active.turns.isEmpty
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
    await _activateSession(
      sessionId: active.sessionId,
      scenarioId: active.scenarioId,
      turns: turns,
    );
  }

  /// Terminer et recommencer: end the 409 pending session, then start again.
  Future<void> replacePending() async {
    final pending = _pendingActive;
    if (pending == null) return;
    _pendingActive = null;
    await ref.read(conversationRepositoryProvider).endSession(pending.sessionId);
    if (!ref.mounted) return;
    await start(
      mode: _pendingMode,
      scenarioId: _pendingScenarioId,
      missionId: _pendingMissionId,
    );
  }

  Future<void> _activateSession({
    required int sessionId,
    required List<ConversationTurn> turns,
    String? scenarioId,
  }) async {
    final speech = ref.read(speechServiceProvider);
    await speech.setLanguage(await _preferredLanguageTag());
    final speechReady = await speech.initialize();
    if (!ref.mounted) return;
    state = ConversationState(
      sessionId: sessionId,
      scenarioId: scenarioId,
      turns: turns,
      error: speechReady ? null : 'Microphone is not available',
    );
    await _loadQuota();
  }

  Future<void> _loadQuota() async {
    try {
      final sub = await ref.read(billingRepositoryProvider).getSubscription();
      if (!ref.mounted || state.sessionId == null) return;
      state = state.copyWith(
        remainingMinutes: sub.remainingMinutes,
        freeDailyMinutes: sub.freeDailyMinutes,
        quotaWarning: sub.quotaWarning,
      );
    } catch (_) {}
  }

  void _failStart(String message, Object error, [StackTrace? stack]) {
    if (ref.mounted) {
      state = ConversationState(error: message);
      ref
          .read(crashReporterProvider)
          .captureError(
            error,
            stack ?? StackTrace.current,
            context: 'ConversationViewModel.start',
          );
    }
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
    if (state.sessionId == null) return;
    // A tap while the last reply is still streaming/playing used to no-op
    // (status != idle) — after a few turns the orb looked dead.
    if (state.status == ConversationStatus.thinking ||
        state.status == ConversationStatus.speaking) {
      await _playback.cancel();
      _loop.stop();
      if (ref.mounted) {
        state = state.copyWith(
          status: ConversationStatus.idle,
          clearPartial: true,
        );
      }
    }
    if (state.status != ConversationStatus.idle) {
      return;
    }
    final config = await ref.read(runtimeConfigProvider.future);
    if (config.conversationServerStt) {
      await _pushToTalk.startRecording();
      return;
    }
    await _loop.run();
  }

  /// Server-STT recording (Écho / tests). The talk orb uses [listenAndRespond].
  Future<void> startPushToTalk() async {
    if (state.sessionId == null || state.status != ConversationStatus.idle) {
      return;
    }
    await _pushToTalk.startRecording();
  }

  /// Second tap while listening: send what was heard. Does not kill the loop.
  Future<void> finishCurrentUtterance() async {
    if (_pushToTalk.isRecording) {
      await _pushToTalk.stopAndRespond();
      return;
    }
    await ref.read(speechServiceProvider).stopListening();
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
      state = state.copyWith(
        status: ConversationStatus.idle,
        clearPartial: true,
      );
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
    if (ref.mounted &&
        state.sessionId != null &&
        state.status != ConversationStatus.idle) {
      state = state.copyWith(
        status: ConversationStatus.idle,
        clearPartial: true,
      );
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

  /// Re-fetches the active session's transcript from the server and replaces
  /// [ConversationState.turns] with it (#312). Triggered when the offline queue
  /// shrinks (a sync just ran): OfflineTurnSync only reports HOW MANY turns it
  /// sent, not their replies, so a replayed turn's reply is otherwise never
  /// shown anywhere.
  ///
  /// Skipped (both before AND after the network call — a turn can start WHILE
  /// the fetch is in flight) unless the conversation is idle, so a stale server
  /// snapshot can never clobber text that is streaming in right now. Also
  /// double-checked against the session id both before and after, so a session
  /// change mid-fetch can't apply the wrong session's turns. `getActiveSession`
  /// only carries role+content (no correction), so any correction chip already
  /// attached locally is preserved by matching it back onto the re-fetched turn
  /// AT THE SAME POSITION (#390) — turns are strictly append-only and this only
  /// runs while idle (guarded above, both before and after the await), so the
  /// local list's order is a stable, correctly-ordered prefix of what the
  /// server just returned. Matching by role+content instead (the previous
  /// approach) collapsed two turns with identical text — e.g. the learner
  /// saying "yes" twice — onto the SAME correction, so a later corrected turn
  /// could leak its chip onto an earlier, uncorrected one with the same words.
  Future<void> _refreshTurnsFromServer() async {
    final sid = state.sessionId;
    if (sid == null || state.status != ConversationStatus.idle) return;
    final ActiveSessionData? active;
    try {
      active = await ref
          .read(conversationRepositoryProvider)
          .getActiveSession();
    } catch (e, s) {
      if (ref.mounted) {
        ref
            .read(crashReporterProvider)
            .captureError(
              e,
              s,
              context:
                  'ConversationViewModel._refreshTurnsFromServer: refetch failed',
            );
      }
      return;
    }
    if (!ref.mounted || active == null) return;
    if (active.sessionId != sid || state.sessionId != sid) return;
    if (state.status != ConversationStatus.idle) return;
    final localTurns = state.turns;
    // The opening bubble is synthesized client-side (start(), ConversationScript.openingMessage)
    // and NEVER persisted, so the server transcript (`active.turns`) always starts at the first
    // USER turn. The bubble is present iff local leads with an assistant turn AND the server does
    // NOT lead with that same turn (server starts at a user turn, or is empty). Align the two
    // real-turn sequences from that head offset: aligning from index 0 shifts every server turn
    // by one when the opening is present, dropping every correction chip and deleting the
    // opening bubble (#400).
    final hasClientOpening =
        localTurns.isNotEmpty &&
        localTurns.first.role == kRoleAssistant &&
        (active.turns.isEmpty || active.turns.first.role == kRoleUser);
    final headOffset = hasClientOpening ? 1 : 0;
    state = state.copyWith(
      turns: [
        // Preserve the client-only opening bubble — the server never has it.
        ...localTurns.take(headOffset),
        for (var i = 0; i < active.turns.length; i++)
          ConversationTurn(
            active.turns[i].role,
            active.turns[i].content,
            // localTurns[headOffset + i] is the local counterpart of server turn i.
            // The role match guards a hypothetical local/server desync at this position;
            // the bound guard covers server turns local hasn't seen yet (the synced tail).
            correction:
                headOffset + i < localTurns.length &&
                    localTurns[headOffset + i].role == active.turns[i].role
                ? localTurns[headOffset + i].correction
                : null,
          ),
      ],
    );
  }

  /// Test hook: await any in-flight background audio playback. Production code
  /// never blocks a turn on playback (it runs in the background by design).
  @visibleForTesting
  Future<void> awaitPlaybackForTest() => _playback.awaitPlayback();
}

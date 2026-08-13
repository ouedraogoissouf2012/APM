import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/providers.dart';
import '../../../data/models/echo.dart';
import '../../../data/repositories/echo_repository.dart';
import 'echo_state.dart';

final echoRepositoryProvider = Provider<EchoRepository>(
  (ref) => EchoRepository(ref.watch(authenticatedApiClientProvider)),
);

final echoViewModelProvider =
    NotifierProvider.autoDispose<EchoViewModel, EchoState>(EchoViewModel.new);

/// Drives one shadowing round: load a target phrase (and synthesize the model
/// voice), let the learner hear the model, record their attempt, score it, then
/// replay their voice against the model (A/B). Network/mic errors go into
/// [EchoState.error] rather than being thrown at the UI.
class EchoViewModel extends Notifier<EchoState> {
  bool _busy = false; // guards re-entrant taps

  @override
  EchoState build() => const EchoState();

  EchoRepository get _repo => ref.read(echoRepositoryProvider);

  /// Marks shadowing unavailable (no server TTS/STT) so the screen can explain
  /// it instead of failing on a 404.
  void markUnavailable() {
    state = state.copyWith(unavailable: true);
  }

  /// Fetches a new phrase and pre-synthesizes the model voice for A/B. Safe to
  /// call to (re)start a round.
  Future<void> loadPhrase() async {
    if (_busy) return;
    _busy = true;
    state = state.copyWith(
      phase: EchoPhase.idle,
      clearError: true,
      clearResult: true,
      clearMyRecording: true,
    );
    try {
      final phrase = await _repo.nextPhrase();
      final clip = await _repo.synthesize(phrase.text);
      if (!ref.mounted) return;
      state = state.copyWith(
        phrase: phrase,
        modelAudioB64: clip.audioB64,
        modelMime: clip.mime,
        phase: EchoPhase.idle,
      );
    } on ApiException catch (e) {
      _fail(e.message);
    } catch (_) {
      _fail('Could not load a phrase. Please try again.');
    } finally {
      _busy = false;
    }
  }

  /// Plays the synthesized model voice (the phrase to imitate). Callable both
  /// before recording (idle) and while reviewing a scored attempt
  /// (reviewing, via the "Modèle" A/B button) — restores whichever phase was
  /// active before playback (#330), instead of always forcing idle: forcing
  /// idle from reviewing would re-arm the orb for a fresh recording while the
  /// score/coaching panel is still on screen (a tap there would start a
  /// stray recording over a frozen result).
  ///
  /// Guarded by [_busy] (#330 code review): without it, a second call landing
  /// while the first is still awaiting playback would itself capture
  /// `restore == EchoPhase.playingModel` (the first call's own transient
  /// phase) — whichever call's restore then writes LAST permanently strands
  /// the orb at playingModel (non-interactive, no self-recovery). [_busy] is
  /// shared with [playMine] so the two can't play concurrently either — both
  /// go through the same speaker, and without this "Ma voix" would stay
  /// enabled (phase == reviewing the whole time it plays, pre-#330-followup)
  /// and cut "Modèle" off mid-clip through the shared player, or vice versa.
  ///
  /// The `catch` (also #330 followup) matters as much as the guard: a
  /// throwing [playClip] (unsupported/corrupt audio, a browser playback
  /// rejection) must still restore the phase, or the orb and every A/B
  /// control gated on `phase == reviewing` go permanently dead — and before
  /// the learner's first listen (`result` still null), there is no "Phrase
  /// suivante" button yet either, so that's a full soft-lock of the screen.
  Future<void> playModel() async {
    if (_busy) return;
    final b64 = state.modelAudioB64;
    if (b64 == null || b64.isEmpty) return;
    _busy = true;
    final restore = state.phase;
    state = state.copyWith(phase: EchoPhase.playingModel);
    var failed = false;
    try {
      await ref.read(audioPlaybackProvider).playClip(b64, state.modelMime);
    } catch (_) {
      failed = true;
    } finally {
      _busy = false;
    }
    if (!ref.mounted) return;
    state = failed
        ? state.copyWith(
            phase: restore,
            error: 'Could not play the model audio.',
          )
        // clearError (final review sweep): copyWith keeps `this.error` by
        // default when no `error` is passed, so without this, a stale
        // message from a PREVIOUS failed playback would keep showing next
        // to A/B controls the learner just successfully replayed.
        : state.copyWith(phase: restore, clearError: true);
  }

  /// Starts recording the learner reading the phrase aloud.
  Future<void> record() async {
    if (_busy || !state.hasPhrase) return;
    final started = await ref.read(audioRecordingProvider).start();
    if (!ref.mounted) return;
    if (!started) {
      _fail('Microphone is not available.');
      return;
    }
    state = state.copyWith(phase: EchoPhase.recording, clearError: true);
  }

  /// Stops recording, keeps the bytes for A/B, and scores the attempt.
  Future<void> stopAndScore() async {
    if (_busy || state.phase != EchoPhase.recording) return;
    _busy = true;
    try {
      final bytes = await ref.read(audioRecordingProvider).stop();
      if (!ref.mounted) return;
      if (bytes == null || bytes.isEmpty) {
        state = state.copyWith(phase: EchoPhase.idle);
        return;
      }
      state = state.copyWith(
        phase: EchoPhase.scoring,
        myRecording: bytes,
        clearCoaching: true,
      );
      final result = await _repo.scoreAttempt(
        audioBytes: bytes,
        targetText: state.phrase!.text,
      );
      if (!ref.mounted) return;
      // Show the score immediately (fast: STT + phonemes). Coaching is fetched
      // afterwards, in the background, so the slow LLM never blocks this display.
      state = state.copyWith(result: result, phase: EchoPhase.reviewing);
      _fetchCoaching(result);
    } on ApiException catch (e) {
      _fail(e.message);
    } catch (_) {
      _fail('Could not score your attempt. Please try again.');
    } finally {
      _busy = false;
    }
  }

  /// Fetches coaching for the missed words AFTER the score is shown, so the slow
  /// coaching LLM never blocks the reactive display. A perfect attempt (no misses)
  /// needs no coaching. A failure here is silent — the score already stands.
  Future<void> _fetchCoaching(AttemptResult result) async {
    if (result.missedWords.isEmpty) return;
    state = state.copyWith(coachingLoading: true);
    try {
      final tip = await _repo.coachAttempt(
        targetText: state.phrase!.text,
        missedWords: result.missedWords,
      );
      if (!ref.mounted) return;
      state = state.copyWith(coaching: tip, coachingLoading: false);
    } catch (_) {
      if (!ref.mounted) return;
      state = state.copyWith(
        coachingLoading: false,
      ); // score stands without a tip
    }
  }

  /// A/B: replays the learner's own recording. Uses playBytes (a blob: URL on
  /// web) — a data: URL of recorded WebM/Opus fails to decode in Chrome.
  ///
  /// Mirrors [playModel]'s phase capture/restore + [_busy] guard (#330
  /// followup): only callable from reviewing, so `restore` is always
  /// `EchoPhase.reviewing`, but it still needs its own transient phase — the
  /// "Modèle" button is gated on `phase == reviewing`, and without this call
  /// leaving that phase during playback, "Modèle" would stay enabled (and
  /// tappable) the whole time "Ma voix" is playing.
  Future<void> playMine() async {
    if (_busy) return;
    final bytes = state.myRecording;
    if (bytes == null || bytes.isEmpty) return;
    _busy = true;
    final restore = state.phase;
    state = state.copyWith(phase: EchoPhase.playingMine);
    var failed = false;
    try {
      await ref.read(audioPlaybackProvider).playBytes(bytes, 'audio/wav');
    } catch (_) {
      failed = true;
    } finally {
      _busy = false;
    }
    if (!ref.mounted) return;
    state = failed
        ? state.copyWith(
            phase: restore,
            error: 'Could not play your recording.',
          )
        // clearError: see the matching comment in playModel() above.
        : state.copyWith(phase: restore, clearError: true);
  }

  /// Moves to the next round (up to [kEchoTotalRounds]) and loads a new phrase.
  ///
  /// Guarded by [_busy] (final review sweep): without it, tapping "Phrase
  /// suivante" while "Modèle"/"Ma voix" is still playing would set
  /// `phase: idle` here and then call [loadPhrase], which itself no-ops on
  /// the same still-held guard — silently skipping the fetch (stale
  /// phrase/result survive) while the in-flight play call's own restore
  /// later overwrites this method's `idle` back to the `reviewing` it
  /// captured before the tap. Net effect: the round counter advances but the
  /// screen keeps showing the previous round's content under the new
  /// number. The "Phrase suivante"/"Terminer" button is also gated on
  /// `phase == reviewing` (echo_screen.dart) so this is a defensive
  /// backstop, not the only guard — consistent with every other public
  /// method on this class already checking [_busy] first.
  Future<void> nextRound() async {
    if (_busy) return;
    final next = state.round + 1;
    state = state.copyWith(round: next, phase: EchoPhase.idle);
    await loadPhrase();
  }

  /// Stops (discarding) an in-progress recording when the learner leaves the
  /// screen or backgrounds the app (#222), so the mic can't stay hot off-screen.
  /// Idempotent — a no-op outside the recording phase.
  Future<void> cancel() async {
    // ref.mounted FIRST: cancel() runs from the screen's dispose, where the
    // provider may already be gone (a disposed ProviderScope in tests / app
    // teardown) — reading `state` or `ref` then throws UnmountedRefException.
    if (!ref.mounted || state.phase != EchoPhase.recording) return;
    await ref.read(audioRecordingProvider).cancel();
    if (ref.mounted) state = state.copyWith(phase: EchoPhase.idle);
  }

  void _fail(String message) {
    if (!ref.mounted) return;
    state = state.copyWith(phase: EchoPhase.idle, error: message);
  }
}

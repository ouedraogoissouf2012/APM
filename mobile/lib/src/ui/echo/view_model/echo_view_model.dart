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
    NotifierProvider.autoDispose<EchoViewModel, EchoState>(
  EchoViewModel.new,
);

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

  /// Plays the synthesized model voice (the phrase to imitate). Restores the
  /// calling phase afterward rather than forcing `idle`, since this is also
  /// callable while reviewing — re-listening must not re-arm the mic orb.
  Future<void> playModel() async {
    final b64 = state.modelAudioB64;
    if (b64 == null || b64.isEmpty || state.phase == EchoPhase.playingModel) {
      return; // already playing — a re-entrant tap must not clobber restore
    }
    final restore = state.phase;
    state = state.copyWith(phase: EchoPhase.playingModel);
    await ref.read(audioPlaybackProvider).playClip(b64, state.modelMime);
    if (!ref.mounted) return;
    state = state.copyWith(phase: restore);
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
      state = state.copyWith(coachingLoading: false); // score stands without a tip
    }
  }

  /// A/B: replays the learner's own recording. Uses playBytes (a blob: URL on
  /// web) — a data: URL of recorded WebM/Opus fails to decode in Chrome.
  Future<void> playMine() async {
    final bytes = state.myRecording;
    if (bytes == null || bytes.isEmpty) return;
    await ref.read(audioPlaybackProvider).playBytes(bytes, 'audio/wav');
  }

  /// Moves to the next round (up to [kEchoTotalRounds]) and loads a new phrase.
  Future<void> nextRound() async {
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

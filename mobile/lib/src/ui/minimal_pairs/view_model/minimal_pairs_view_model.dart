import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/providers.dart';
import '../../../core/observability/providers.dart';
import '../../../data/models/minimal_pairs.dart';
import '../../../data/repositories/minimal_pairs_repository.dart';
import 'minimal_pairs_state.dart';

final minimalPairsRepositoryProvider = Provider<MinimalPairsRepository>(
  (ref) => MinimalPairsRepository(ref.watch(authenticatedApiClientProvider)),
);

final minimalPairsViewModelProvider =
    NotifierProvider.autoDispose<MinimalPairsViewModel, MinimalPairsState>(
      MinimalPairsViewModel.new,
    );

/// Drives one minimal-pair round: draw a pair + one of its words, have Ava say
/// it, let the learner guess which they heard (discrimination), then have them
/// produce it (recording scored by the backend). Errors go into state.error.
class MinimalPairsViewModel extends Notifier<MinimalPairsState> {
  final Random _random = Random();
  bool _busy = false;

  @override
  MinimalPairsState build() => const MinimalPairsState();

  MinimalPairsRepository get _repo => ref.read(minimalPairsRepositoryProvider);

  void markUnavailable() {
    state = state.copyWith(unavailable: true);
  }

  /// Draws a pair and one of its two words, synthesizes that word, and moves to
  /// the discrimination step.
  Future<void> loadPair() async {
    if (_busy) return;
    _busy = true;
    state = state.copyWith(
      phase: PairPhase.idle,
      clearError: true,
      clearGuess: true,
      clearAttempt: true,
      clearRecording: true,
    );
    try {
      final pair = kMinimalPairs[_random.nextInt(kMinimalPairs.length)];
      final spoken = _random.nextBool() ? pair.wordA : pair.wordB;
      final clip = await _repo.synthesize(spoken);
      if (!ref.mounted) return;
      state = state.copyWith(
        pair: pair,
        spokenWord: spoken,
        spokenAudioB64: clip.audioB64,
        spokenMime: clip.mime,
        phase: PairPhase.guessing,
      );
    } on ApiException catch (e) {
      _fail(e.message);
    } catch (e, s) {
      // (#351) An unexpected (non-ApiException) failure would otherwise
      // vanish silently — report it so a recurring cause is visible instead
      // of just "loading failed" reports with no trail.
      _reportError(e, s, 'MinimalPairsViewModel.loadPair');
      _fail('Could not load a pair. Please try again.');
    } finally {
      _busy = false;
    }
  }

  /// Replays the word Ava spoke (the learner can listen again before guessing).
  ///
  /// Guarded/wrapped like EchoViewModel.playModel (#343): [_busy] — shared with
  /// [playMine] — stops a rapid double-tap running two clips at once (whichever
  /// restore lands LAST would otherwise strand the phase at `playing`), and the
  /// try/catch guarantees the phase is restored even if playClip throws
  /// (unsupported/corrupt audio, a browser rejection) — without it, an exception
  /// leaks out and leaves the orb frozen at `playing` with no recovery. Restores
  /// the phase captured BEFORE playback rather than a `wasGuessing` special-case,
  /// which mis-restored to the transient `playing` phase when called outside
  /// guessing.
  Future<void> playWord() async {
    if (_busy) return;
    final b64 = state.spokenAudioB64;
    if (b64 == null || b64.isEmpty) return;
    _busy = true;
    final restore = state.phase;
    state = state.copyWith(phase: PairPhase.playing);
    var failed = false;
    try {
      await ref.read(audioPlaybackProvider).playClip(b64, state.spokenMime);
    } catch (_) {
      failed = true;
    } finally {
      _busy = false;
    }
    if (!ref.mounted) return;
    state = failed
        ? state.copyWith(phase: restore, error: 'Could not play the word.')
        : state.copyWith(phase: restore, clearError: true);
  }

  /// Records the learner's discrimination choice and reveals correct/incorrect.
  void guess(String word) {
    if (state.phase != PairPhase.guessing) return;
    state = state.copyWith(guess: word, phase: PairPhase.guessed);
  }

  /// Starts recording the learner producing the word.
  Future<void> record() async {
    if (_busy || !state.hasPair) return;
    final started = await ref.read(audioRecordingProvider).start();
    if (!ref.mounted) return;
    if (!started) {
      _fail('Microphone is not available.');
      return;
    }
    state = state.copyWith(phase: PairPhase.recording, clearError: true);
  }

  /// Stops recording, keeps the bytes for replay, and scores the production
  /// against the pair (target = the spoken word, other = the pair's other word).
  Future<void> stopAndScore() async {
    if (_busy || state.phase != PairPhase.recording) return;
    _busy = true;
    try {
      final bytes = await ref.read(audioRecordingProvider).stop();
      if (!ref.mounted) return;
      if (bytes == null || bytes.isEmpty) {
        state = state.copyWith(phase: PairPhase.guessed);
        return;
      }
      final pair = state.pair!;
      final target = state.spokenWord!;
      final other = target == pair.wordA ? pair.wordB : pair.wordA;
      state = state.copyWith(phase: PairPhase.scoring, myRecording: bytes);
      final attempt = await _repo.scoreAttempt(
        audioBytes: bytes,
        target: target,
        other: other,
      );
      if (!ref.mounted) return;
      state = state.copyWith(attempt: attempt, phase: PairPhase.reviewing);
    } on ApiException catch (e) {
      _fail(e.message);
    } catch (e, s) {
      // (#351) see the matching comment in loadPair() above.
      _reportError(e, s, 'MinimalPairsViewModel.stopAndScore');
      _fail('Could not score your attempt. Please try again.');
    } finally {
      _busy = false;
    }
  }

  /// Replays the learner's own production recording. Shares [_busy] with
  /// [playWord] (#343) so the two can't play over each other on the one speaker,
  /// and a double-tap can't stack two playbacks; a throwing playBytes surfaces
  /// an error instead of leaking out.
  Future<void> playMine() async {
    if (_busy) return;
    final bytes = state.myRecording;
    if (bytes == null || bytes.isEmpty) return;
    _busy = true;
    try {
      await ref.read(audioPlaybackProvider).playBytes(bytes, 'audio/wav');
    } catch (e, s) {
      // (#351) see the matching comment in loadPair() above.
      _reportError(e, s, 'MinimalPairsViewModel.playMine');
      if (ref.mounted) {
        state = state.copyWith(error: 'Could not play your recording.');
      }
    } finally {
      _busy = false;
    }
  }

  /// Advances to the next round (up to [kMinimalPairsTotalRounds]).
  ///
  /// Guarded by [_busy] (#350): without it, tapping "Paire suivante" while
  /// [playMine] is still awaiting playback would overwrite state to `idle`
  /// (round advanced, no clear flags) here, and then [loadPair] itself
  /// no-ops on the still-held guard — the `idle` phase has no interactive
  /// body (minimal_pairs_screen.dart's `_Body` switch), stranding the
  /// learner on a blank screen with no self-recovery even after the
  /// in-flight playback finishes. Mirrors echo_view_model.dart's
  /// [EchoViewModel.nextRound] guard (#330 followup).
  Future<void> nextRound() async {
    if (_busy) return;
    state = state.copyWith(round: state.round + 1, phase: PairPhase.idle);
    await loadPair();
  }

  /// Stops (discarding) an in-progress production recording when the learner
  /// leaves the screen or backgrounds the app (#222), so the mic can't stay hot
  /// off-screen. Returns to the pre-record 'guessed' step so the round can be
  /// resumed. Idempotent — a no-op outside the recording phase.
  Future<void> cancel() async {
    // ref.mounted FIRST: cancel() runs from the screen's dispose, where the
    // provider may already be gone (a disposed ProviderScope in tests / app
    // teardown) — reading `state` or `ref` then throws UnmountedRefException.
    if (!ref.mounted || state.phase != PairPhase.recording) return;
    await ref.read(audioRecordingProvider).cancel();
    if (ref.mounted) state = state.copyWith(phase: PairPhase.guessed);
  }

  void _fail(String message) {
    if (!ref.mounted) return;
    state = state.copyWith(phase: PairPhase.idle, error: message);
  }

  /// Reports an unexpected exception (#351), guarding the read behind
  /// [ref.mounted] — this is an autoDispose provider, so a `Ref` read after
  /// disposal throws, and a crash report must never itself become the crash.
  void _reportError(Object error, StackTrace stack, String context) {
    if (!ref.mounted) return;
    ref.read(crashReporterProvider).captureError(error, stack, context: context);
  }
}

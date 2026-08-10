import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/providers.dart';
import '../../../data/models/minimal_pairs.dart';
import '../../../data/repositories/minimal_pairs_repository.dart';
import 'minimal_pairs_state.dart';

final minimalPairsRepositoryProvider = Provider<MinimalPairsRepository>(
  (ref) => MinimalPairsRepository(ref.watch(authenticatedApiClientProvider)),
);

final minimalPairsViewModelProvider =
    NotifierProvider<MinimalPairsViewModel, MinimalPairsState>(
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
    } catch (_) {
      _fail('Could not load a pair. Please try again.');
    } finally {
      _busy = false;
    }
  }

  /// Replays the word Ava spoke (the learner can listen again before guessing).
  Future<void> playWord() async {
    final b64 = state.spokenAudioB64;
    if (b64 == null || b64.isEmpty) return;
    final wasGuessing = state.phase == PairPhase.guessing;
    state = state.copyWith(phase: PairPhase.playing);
    await ref.read(audioPlaybackProvider).playClip(b64, state.spokenMime);
    if (!ref.mounted) return;
    state = state.copyWith(phase: wasGuessing ? PairPhase.guessing : state.phase);
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
    } catch (_) {
      _fail('Could not score your attempt. Please try again.');
    } finally {
      _busy = false;
    }
  }

  /// Replays the learner's own production recording.
  Future<void> playMine() async {
    final bytes = state.myRecording;
    if (bytes == null || bytes.isEmpty) return;
    await ref.read(audioPlaybackProvider).playBytes(bytes, 'audio/wav');
  }

  /// Advances to the next round (up to [kMinimalPairsTotalRounds]).
  Future<void> nextRound() async {
    state = state.copyWith(round: state.round + 1, phase: PairPhase.idle);
    await loadPair();
  }

  /// Stops (discarding) an in-progress production recording when the learner
  /// leaves the screen or backgrounds the app (#222), so the mic can't stay hot
  /// off-screen. Returns to the pre-record 'guessed' step so the round can be
  /// resumed. Idempotent — a no-op outside the recording phase.
  Future<void> cancel() async {
    if (state.phase != PairPhase.recording) return;
    await ref.read(audioRecordingProvider).cancel();
    if (ref.mounted) state = state.copyWith(phase: PairPhase.guessed);
  }

  void _fail(String message) {
    if (!ref.mounted) return;
    state = state.copyWith(phase: PairPhase.idle, error: message);
  }
}

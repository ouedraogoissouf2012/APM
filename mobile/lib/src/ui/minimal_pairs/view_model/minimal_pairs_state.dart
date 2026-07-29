import 'dart:typed_data';

import '../../../data/models/minimal_pairs.dart';
import '../../../data/repositories/minimal_pairs_repository.dart';

/// Where the learner is in one minimal-pair round: first they discriminate
/// (Ava says one word, they guess which), then they produce (say it themselves).
enum PairPhase {
  idle,

  /// Ava is speaking the drawn word.
  playing,

  /// Waiting for the learner to guess which word they heard.
  guessing,

  /// The guess has been checked; showing correct/incorrect.
  guessed,

  /// Recording the learner producing the word.
  recording,

  /// Uploading + scoring the production.
  scoring,

  /// Showing the production result (said target / said the other / coaching).
  reviewing,
}

const int kMinimalPairsTotalRounds = 5;

class MinimalPairsState {
  const MinimalPairsState({
    this.phase = PairPhase.idle,
    this.pair,
    this.spokenWord,
    this.spokenAudioB64,
    this.spokenMime = 'audio/mpeg',
    this.guess,
    this.myRecording,
    this.attempt,
    this.round = 1,
    this.error,
    this.unavailable = false,
  });

  final PairPhase phase;
  final MinimalPair? pair;

  /// The word Ava actually spoke this round (the correct answer to the guess).
  final String? spokenWord;
  final String? spokenAudioB64;
  final String spokenMime;

  /// The word the learner tapped in the discrimination step (null until they do).
  final String? guess;

  /// The learner's production recording, kept locally for replay.
  final Uint8List? myRecording;
  final PairAttempt? attempt;

  final int round;
  final String? error;
  final bool unavailable;

  bool get hasPair => pair != null;
  bool get guessedCorrectly => guess != null && guess == spokenWord;
  bool get isLastRound => round >= kMinimalPairsTotalRounds;

  MinimalPairsState copyWith({
    PairPhase? phase,
    MinimalPair? pair,
    String? spokenWord,
    String? spokenAudioB64,
    String? spokenMime,
    String? guess,
    Uint8List? myRecording,
    PairAttempt? attempt,
    int? round,
    String? error,
    bool? unavailable,
    bool clearError = false,
    bool clearGuess = false,
    bool clearAttempt = false,
    bool clearRecording = false,
  }) {
    return MinimalPairsState(
      phase: phase ?? this.phase,
      pair: pair ?? this.pair,
      spokenWord: spokenWord ?? this.spokenWord,
      spokenAudioB64: spokenAudioB64 ?? this.spokenAudioB64,
      spokenMime: spokenMime ?? this.spokenMime,
      guess: clearGuess ? null : (guess ?? this.guess),
      myRecording: clearRecording ? null : (myRecording ?? this.myRecording),
      attempt: clearAttempt ? null : (attempt ?? this.attempt),
      round: round ?? this.round,
      error: clearError ? null : (error ?? this.error),
      unavailable: unavailable ?? this.unavailable,
    );
  }
}

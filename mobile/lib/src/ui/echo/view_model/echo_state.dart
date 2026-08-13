import 'dart:typed_data';

import '../../../data/models/echo.dart';

/// Where the learner is in one shadowing round.
enum EchoPhase {
  /// No phrase loaded yet, or between rounds.
  idle,

  /// Playing the model voice (the phrase to imitate).
  playingModel,

  /// Recording the learner reading the phrase aloud.
  recording,

  /// Uploading + scoring the attempt.
  scoring,

  /// Showing the result: missed words, coaching, and A/B replay.
  reviewing,

  /// Playing back the learner's own recording (A/B "Ma voix"), from reviewing.
  playingMine,
}

const int kEchoTotalRounds =
    5; // ~5 reps per phrase then a plateau (Shiki 2010)

class EchoState {
  const EchoState({
    this.phase = EchoPhase.idle,
    this.phrase,
    this.modelAudioB64,
    this.modelMime = 'audio/mpeg',
    this.myRecording,
    this.result,
    this.coaching,
    this.coachingLoading = false,
    this.round = 1,
    this.error,
    this.unavailable = false,
  });

  final EchoPhase phase;
  final ShadowingPhrase? phrase;

  /// Base64 of the synthesized model voice for the current phrase (for A/B).
  final String? modelAudioB64;
  final String modelMime;

  /// The learner's last recording, kept locally only so they can replay it
  /// against the model (A/B). Never uploaded except transiently for scoring.
  final Uint8List? myRecording;

  final AttemptResult? result;

  /// Coaching tip on the missed words, fetched AFTER the result is shown so the
  /// slow coaching LLM never blocks the reactive score display. Null until it
  /// arrives; [coachingLoading] is true while the deferred call is in flight.
  final String? coaching;
  final bool coachingLoading;

  final int round;
  final String? error;

  /// True when the backend has no server TTS/STT, so shadowing cannot run.
  /// A distinct state (not an error) so the UI shows an honest explanation.
  final bool unavailable;

  bool get hasPhrase => phrase != null;
  bool get canReplayMine => myRecording != null && myRecording!.isNotEmpty;
  bool get isLastRound => round >= kEchoTotalRounds;

  EchoState copyWith({
    EchoPhase? phase,
    ShadowingPhrase? phrase,
    String? modelAudioB64,
    String? modelMime,
    Uint8List? myRecording,
    AttemptResult? result,
    String? coaching,
    bool? coachingLoading,
    int? round,
    String? error,
    bool? unavailable,
    bool clearError = false,
    bool clearResult = false,
    bool clearMyRecording = false,
    bool clearCoaching = false,
  }) {
    return EchoState(
      phase: phase ?? this.phase,
      phrase: phrase ?? this.phrase,
      modelAudioB64: modelAudioB64 ?? this.modelAudioB64,
      modelMime: modelMime ?? this.modelMime,
      myRecording: clearMyRecording ? null : (myRecording ?? this.myRecording),
      result: clearResult ? null : (result ?? this.result),
      coaching: clearCoaching ? null : (coaching ?? this.coaching),
      coachingLoading: coachingLoading ?? this.coachingLoading,
      round: round ?? this.round,
      error: clearError ? null : (error ?? this.error),
      unavailable: unavailable ?? this.unavailable,
    );
  }
}

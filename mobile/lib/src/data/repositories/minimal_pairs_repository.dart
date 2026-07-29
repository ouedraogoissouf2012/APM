import '../../core/network/authenticated_api_client.dart';
import 'echo_repository.dart' show AudioClip;

/// Result of producing one word of a minimal pair. Mirrors the backend
/// `POST /minimal-pairs/attempt` response.
class PairAttempt {
  const PairAttempt({
    required this.transcript,
    required this.saidTarget,
    required this.saidOther,
    this.coaching = '',
  });

  final String transcript;
  final bool saidTarget;
  final bool saidOther;
  final String coaching;

  factory PairAttempt.fromJson(Map<String, dynamic> json) => PairAttempt(
    transcript: json['transcript'] as String? ?? '',
    saidTarget: json['said_target'] as bool? ?? false,
    saidOther: json['said_other'] as bool? ?? false,
    coaching: json['coaching'] as String? ?? '',
  );
}

/// Talks to the backend for the minimal-pairs drill (auth required). The pairs
/// themselves are static (kMinimalPairs); the backend only speaks a word (/tts)
/// and scores a spoken attempt.
class MinimalPairsRepository {
  MinimalPairsRepository(this._api);

  final AuthenticatedApiClient _api;

  /// Synthesizes one word to Ava's neural voice (for the discrimination step).
  Future<AudioClip> synthesize(String word) async {
    final json = await _api.postJson('/tts', body: {'text': word});
    return AudioClip(
      json['audio'] as String? ?? '',
      json['mime'] as String? ?? 'audio/mpeg',
    );
  }

  /// Scores a spoken attempt: did the learner say [target], or [other] instead?
  Future<PairAttempt> scoreAttempt({
    required List<int> audioBytes,
    required String target,
    required String other,
  }) async {
    final json = await _api.postBytes(
      '/minimal-pairs/attempt',
      bytes: audioBytes,
      field: 'audio',
      filename: 'speech.wav',
      fields: {'target': target, 'other': other},
    );
    return PairAttempt.fromJson(json);
  }
}

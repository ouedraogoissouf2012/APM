import '../../core/network/authenticated_api_client.dart';
import '../models/echo.dart';

/// One synthesized audio clip (base64) plus its mime, from `POST /tts`.
class AudioClip {
  const AudioClip(this.audioB64, this.mime);
  final String audioB64;
  final String mime;
}

/// Talks to the backend shadowing endpoints (auth required).
class EchoRepository {
  EchoRepository(this._api);

  final AuthenticatedApiClient _api;

  /// A new target phrase adapted to the learner's level.
  Future<ShadowingPhrase> nextPhrase() async {
    final json = await _api.postJson('/shadowing/phrase');
    return ShadowingPhrase.fromJson(json);
  }

  /// Synthesizes [text] to a neural model voice (the phrase to imitate).
  Future<AudioClip> synthesize(String text) async {
    final json = await _api.postJson('/tts', body: {'text': text});
    return AudioClip(
      json['audio'] as String? ?? '',
      json['mime'] as String? ?? 'audio/mpeg',
    );
  }

  /// Scores a spoken attempt: uploads the recording + the target phrase, gets
  /// back the missed words and coaching.
  Future<AttemptResult> scoreAttempt({
    required List<int> audioBytes,
    required String targetText,
  }) async {
    final json = await _api.postBytes(
      '/shadowing/attempt',
      bytes: audioBytes,
      field: 'audio',
      filename: 'speech.wav',
      fields: {'target_text': targetText},
    );
    return AttemptResult.fromJson(json);
  }
}

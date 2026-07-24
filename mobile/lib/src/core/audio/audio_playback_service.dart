import 'package:audioplayers/audioplayers.dart';

/// Plays synthesized reply audio streamed from the backend. Abstracted so the
/// conversation view model can be unit-tested with an in-memory fake instead of
/// the real platform player.
abstract class AudioPlaybackService {
  /// Plays one base64-encoded audio clip and completes when playback finishes,
  /// so the caller can chain the next clip / next listen right after.
  Future<void> playClip(String audioB64, String mime);

  Future<void> stop();
}

class DeviceAudioPlaybackService implements AudioPlaybackService {
  final AudioPlayer _player = AudioPlayer();

  @override
  Future<void> playClip(String audioB64, String mime) async {
    // A `data:` URL via UrlSource plays reliably on web AND mobile — the browser
    // decodes it natively. BytesSource is "platform-dependent" and often silent
    // on Flutter web, which is exactly the surface this app is tested on.
    final source = UrlSource('data:$mime;base64,$audioB64');
    // Subscribe to completion BEFORE starting playback so a very short clip
    // cannot finish before we listen. A timeout guards against a clip that never
    // signals completion (e.g. a web decode error) freezing the conversation.
    final completed = _player.onPlayerComplete.first;
    await _player.play(source);
    await completed.timeout(const Duration(seconds: 20), onTimeout: () {});
  }

  @override
  Future<void> stop() => _player.stop();
}

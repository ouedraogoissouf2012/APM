import 'dart:convert';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';

/// Plays synthesized reply audio streamed from the backend. Abstracted so the
/// conversation view model can be unit-tested with an in-memory fake instead of
/// the real platform player.
abstract class AudioPlaybackService {
  /// Plays one base64-encoded audio clip and completes when playback finishes,
  /// so the caller can chain the next clip / next listen right after.
  Future<void> playClip(String audioB64, String mime);

  /// Plays raw recorded bytes (the learner's own recording, for A/B). Recording
  /// uses WAV (a complete, self-describing container), so a data: URL of it
  /// decodes cleanly here — unlike streamed WebM/Opus.
  Future<void> playBytes(Uint8List bytes, String mime);

  Future<void> stop();
}

class DeviceAudioPlaybackService implements AudioPlaybackService {
  final AudioPlayer _player = AudioPlayer();

  @override
  Future<void> playClip(String audioB64, String mime) async {
    // A `data:` URL via UrlSource plays reliably on web AND mobile — the browser
    // decodes it natively. BytesSource is "platform-dependent" and often silent
    // on Flutter web, which is exactly the surface this app is tested on.
    await _playSource(UrlSource('data:$mime;base64,$audioB64'));
  }

  @override
  Future<void> playBytes(Uint8List bytes, String mime) async {
    await _playSource(UrlSource('data:$mime;base64,${base64Encode(bytes)}'));
  }

  Future<void> _playSource(Source source) async {
    // Subscribe to completion BEFORE starting playback so a very short clip
    // cannot finish before we listen. Race the completion against a timeout so a
    // clip that never signals completion (e.g. a web decode error) cannot freeze
    // the flow. `Future.any` avoids `.timeout`'s typed onTimeout callback, which
    // fails DDC's strict type check on web.
    final completed = _player.onPlayerComplete.first;
    await _player.play(source);
    await Future.any<void>([
      completed,
      Future<void>.delayed(const Duration(seconds: 20)),
    ]);
  }

  @override
  Future<void> stop() => _player.stop();
}

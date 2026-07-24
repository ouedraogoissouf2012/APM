import 'dart:convert';

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
    final bytes = base64Decode(audioB64);
    // Subscribe to completion BEFORE starting playback, so a very short clip
    // that finishes immediately cannot slip past us and hang the turn.
    final completed = _player.onPlayerComplete.first;
    await _player.play(BytesSource(bytes, mimeType: mime));
    await completed;
  }

  @override
  Future<void> stop() => _player.stop();
}

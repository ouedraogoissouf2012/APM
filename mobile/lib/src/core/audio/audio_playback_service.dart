import 'dart:convert';
import 'dart:typed_data';

// On web, use a native <audio> element (audioplayers' web/FFmpeg backend plays
// data: URLs silently). Off web, use audioplayers. Same WebAudioPlayer API.
import 'native_player.dart' if (dart.library.js_interop) 'web_player.dart';

/// Plays synthesized reply audio streamed from the backend. Abstracted so the
/// conversation view model can be unit-tested with an in-memory fake instead of
/// the real platform player.
abstract class AudioPlaybackService {
  /// Plays one base64-encoded audio clip and completes when playback finishes,
  /// so the caller can chain the next clip / next listen right after.
  Future<void> playClip(String audioB64, String mime);

  /// Plays raw recorded bytes (the learner's own recording, for A/B).
  Future<void> playBytes(Uint8List bytes, String mime);

  Future<void> stop();
}

class DeviceAudioPlaybackService implements AudioPlaybackService {
  final WebAudioPlayer _player = WebAudioPlayer();

  @override
  Future<void> playClip(String audioB64, String mime) =>
      _player.play('data:$mime;base64,$audioB64');

  @override
  Future<void> playBytes(Uint8List bytes, String mime) =>
      _player.play('data:$mime;base64,${base64Encode(bytes)}');

  @override
  Future<void> stop() => _player.stop();

  Future<void> dispose() => _player.dispose();
}

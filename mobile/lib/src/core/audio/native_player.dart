import 'package:audioplayers/audioplayers.dart';

import 'playback_gate.dart';

/// Non-web (mobile/desktop) player: audioplayers works fine off the web. Kept
/// behind the same interface as the web player so the service is platform-blind.
class WebAudioPlayer {
  final AudioPlayer _player = AudioPlayer();
  final PlaybackGate _gate = PlaybackGate();

  Future<void> play(String url) async {
    // Stop whatever the previous clip was doing first (mirrors web_player.dart)
    // so overlapping play() calls can never both hold the gate at once.
    await stop();
    final completer = _gate.start();
    final sub = _player.onPlayerComplete.listen((_) => _gate.complete());
    try {
      await _player.play(UrlSource(url));
      await completer.future.timeout(const Duration(seconds: 20), onTimeout: () {});
    } finally {
      await sub.cancel();
      _gate.clear(completer);
    }
  }

  Future<void> stop() async {
    // Unblocks an in-flight play() immediately (#314) — audioplayers' stop()
    // does not itself fire onPlayerComplete.
    _gate.complete();
    await _player.stop();
  }

  Future<void> dispose() => _player.dispose();
}

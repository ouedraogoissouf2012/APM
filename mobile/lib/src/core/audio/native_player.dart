import 'package:audioplayers/audioplayers.dart';

/// Non-web (mobile/desktop) player: audioplayers works fine off the web. Kept
/// behind the same interface as the web player so the service is platform-blind.
class WebAudioPlayer {
  final AudioPlayer _player = AudioPlayer();

  Future<void> play(String url) async {
    final completed = _player.onPlayerComplete.first;
    await _player.play(UrlSource(url));
    await Future.any<void>([
      completed,
      Future<void>.delayed(const Duration(seconds: 20)),
    ]);
  }

  Future<void> stop() => _player.stop();

  Future<void> dispose() => _player.dispose();
}

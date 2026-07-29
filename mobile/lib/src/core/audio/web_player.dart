import 'dart:async';
import 'dart:js_interop';

import 'package:web/web.dart' as web;

/// Plays audio on the web via a NATIVE HTMLAudioElement.
///
/// Why not audioplayers on web: its web backend routes audio through FFmpeg,
/// which silently fails to play `data:` URLs (both MP3 and recorded WAV) in this
/// app's Chrome build — no error, just no sound. A plain <audio> element decodes
/// the same data URL natively and plays reliably (verified against a real
/// edge-tts MP3). Non-web platforms use the audioplayers path (see the stub).
class WebAudioPlayer {
  web.HTMLAudioElement? _audio;

  /// Plays [url] (a data:/blob: URL) and completes when playback ends or errors,
  /// so callers can chain the next clip. A 20 s guard prevents a hang.
  Future<void> play(String url) async {
    await stop();
    final audio = web.HTMLAudioElement()..src = url;
    _audio = audio;
    final done = Completer<void>();
    final handler = ((web.Event _) {
      if (!done.isCompleted) done.complete();
    }).toJS;
    audio.addEventListener('ended', handler);
    audio.addEventListener('error', handler);
    try {
      await audio.play().toDart;
      await done.future.timeout(const Duration(seconds: 20), onTimeout: () {});
    } finally {
      audio.removeEventListener('ended', handler);
      audio.removeEventListener('error', handler);
    }
  }

  Future<void> stop() async {
    final audio = _audio;
    if (audio != null) {
      audio.pause();
      _audio = null;
    }
  }
}

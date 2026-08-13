import 'dart:js_interop';

import 'package:web/web.dart' as web;

import 'playback_gate.dart';

/// Plays audio on the web via a NATIVE HTMLAudioElement.
///
/// Why not audioplayers on web: its web backend routes audio through FFmpeg,
/// which silently fails to play `data:` URLs (both MP3 and recorded WAV) in this
/// app's Chrome build — no error, just no sound. A plain <audio> element decodes
/// the same data URL natively and plays reliably (verified against a real
/// edge-tts MP3). Non-web platforms use the audioplayers path (see the stub).
class WebAudioPlayer {
  web.HTMLAudioElement? _audio;
  final PlaybackGate _gate = PlaybackGate();

  /// Plays [url] (a data:/blob: URL) and completes when playback ends, errors,
  /// or is stopped, so callers can chain the next clip. A 20 s guard prevents
  /// a hang if none of those ever fire.
  Future<void> play(String url) async {
    await stop();
    final audio = web.HTMLAudioElement()..src = url;
    _audio = audio;
    final completer = _gate.start();
    final handler = ((web.Event _) => _gate.complete()).toJS;
    audio.addEventListener('ended', handler);
    audio.addEventListener('error', handler);
    try {
      await audio.play().toDart;
      await completer.future.timeout(const Duration(seconds: 20), onTimeout: () {});
    } finally {
      audio.removeEventListener('ended', handler);
      audio.removeEventListener('error', handler);
      _gate.clear(completer);
    }
  }

  Future<void> stop() async {
    // Unblocks an in-flight play() immediately (#314) — pause() fires neither
    // 'ended' nor 'error'.
    _gate.complete();
    final audio = _audio;
    if (audio != null) {
      audio.pause();
      _audio = null;
    }
  }

  Future<void> dispose() async {
    await stop();
  }
}

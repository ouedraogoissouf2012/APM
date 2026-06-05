import 'dart:async';

import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

/// On-device speech: recognition (STT) and synthesis (TTS). Free, no API keys —
/// the device/browser engines do the work. Abstracted so the ViewModel is testable.
abstract class SpeechService {
  Future<bool> initialize();

  /// Listens for a single utterance and resolves with the recognized text
  /// (empty string if nothing was understood).
  Future<String> listenOnce();

  Future<void> speak(String text);

  Future<void> stopListening();
}

class DeviceSpeechService implements SpeechService {
  final stt.SpeechToText _stt = stt.SpeechToText();
  final FlutterTts _tts = FlutterTts();

  bool _ready = false;
  Completer<String>? _turn;
  String _captured = '';

  @override
  Future<bool> initialize() async {
    _ready = await _stt.initialize(onStatus: _onStatus);
    await _tts.setLanguage('en-US');
    await _tts.awaitSpeakCompletion(true);
    return _ready;
  }

  void _onStatus(String status) {
    if ((status == 'done' || status == 'notListening') &&
        _turn != null &&
        !_turn!.isCompleted) {
      _turn!.complete(_captured.trim());
    }
  }

  @override
  Future<String> listenOnce() async {
    if (!_ready) return '';
    _captured = '';
    _turn = Completer<String>();
    await _stt.listen(onResult: (r) => _captured = r.recognizedWords);
    return _turn!.future;
  }

  @override
  Future<void> speak(String text) => _tts.speak(text);

  @override
  Future<void> stopListening() => _stt.stop();
}

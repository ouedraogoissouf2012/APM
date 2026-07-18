import 'dart:async';

import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

/// Maps the learner's accent preference (profile: 'us' | 'uk') to the BCP-47
/// tag used for both recognition and synthesis. Unknown/absent -> US English.
String languageTagForAccent(String? accent) =>
    accent == 'uk' ? 'en-GB' : 'en-US';

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
  /// [languageTag] is the BCP-47 language the learner practises in. Both the
  /// recognizer and the synthesizer are pinned to it, otherwise the device
  /// default locale (e.g. French) hijacks recognition and English speech gets
  /// transcribed as garbage — fatal for an English-practice app.
  DeviceSpeechService({this.languageTag = 'en-US'});

  /// TTS rate, slightly below default: a clearer model for a learner's ear.
  static const double kLearnerSpeechRate = 0.45;

  final String languageTag;

  final stt.SpeechToText _stt = stt.SpeechToText();
  final FlutterTts _tts = FlutterTts();

  bool _ready = false;
  // Resolved to a locale the recognizer actually supports (device locale IDs
  // vary: 'en-US' vs 'en_US'); falls back to [languageTag] when unknown.
  late String _sttLocaleId = languageTag;
  Completer<String>? _turn;
  String _captured = '';

  @override
  Future<bool> initialize() async {
    _ready = await _stt.initialize(onStatus: _onStatus);
    if (_ready) {
      _sttLocaleId = await _resolveRecognitionLocale();
    }
    await _tts.setLanguage(languageTag);
    await _tts.setSpeechRate(kLearnerSpeechRate);
    await _tts.awaitSpeakCompletion(true);
    return _ready;
  }

  /// Picks the recognizer locale matching [languageTag]'s language (e.g. any
  /// `en*`), preferring an exact tag match. Falls back to [languageTag] when the
  /// device exposes no locales (common on web).
  Future<String> _resolveRecognitionLocale() async {
    final want = _normalize(languageTag);
    final language = want.split('-').first;
    try {
      final locales = await _stt.locales();
      if (locales.isEmpty) return languageTag;
      final sameLanguage = locales
          .where((l) => _normalize(l.localeId).split('-').first == language)
          .toList();
      if (sameLanguage.isEmpty) return languageTag;
      final exact = sameLanguage.where((l) => _normalize(l.localeId) == want);
      return exact.isNotEmpty ? exact.first.localeId : sameLanguage.first.localeId;
    } catch (_) {
      return languageTag;
    }
  }

  static String _normalize(String localeId) =>
      localeId.toLowerCase().replaceAll('_', '-');

  void _onStatus(String status) {
    if ((status == 'done' || status == 'notListening') &&
        _turn != null &&
        !_turn!.isCompleted) {
      _turn!.complete(_captured.trim());
    }
  }

  @override
  Future<String> listenOnce() async {
    // Lazy init: the service may be recreated (e.g. accent change) after the
    // conversation already called initialize() on the previous instance.
    if (!_ready) {
      await initialize();
      if (!_ready) return '';
    }
    _captured = '';
    _turn = Completer<String>();
    await _stt.listen(
      onResult: (r) => _captured = r.recognizedWords,
      listenOptions: stt.SpeechListenOptions(
        localeId: _sttLocaleId,
        partialResults: true,
      ),
    );
    return _turn!.future;
  }

  @override
  Future<void> speak(String text) => _tts.speak(text);

  @override
  Future<void> stopListening() => _stt.stop();
}

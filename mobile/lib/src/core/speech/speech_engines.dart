import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

/// Thin ports over the two device plugins, so [DeviceSpeechService] depends on
/// interfaces (DIP) and can be unit-tested with in-memory fakes instead of the
/// real process-wide singletons.
///
/// These deliberately mirror only the slice of each plugin the service uses.

/// Recognition (STT) port.
abstract class SttEngine {
  Future<bool> initialize({
    required void Function(String status) onStatus,
    required void Function(String error) onError,
  });

  Future<List<String>> localeIds();

  /// Starts a single listen session. [onResult] fires for partial and final
  /// results; [isFinal] marks the terminal one. [pauseFor] ends listening after
  /// that much trailing silence; [listenFor] caps the whole utterance.
  Future<void> listen({
    required String localeId,
    required void Function(String words, bool isFinal) onResult,
    required Duration pauseFor,
    required Duration listenFor,
  });

  Future<void> stop();
}

/// Synthesis (TTS) port.
abstract class TtsEngine {
  Future<void> configure({required String languageTag, required double rate});

  /// Speaks [text] and completes only when the utterance finishes.
  Future<void> speak(String text);

  Future<void> stop();
}

/// Real STT backed by `speech_to_text`.
class PluginSttEngine implements SttEngine {
  final stt.SpeechToText _stt = stt.SpeechToText();

  @override
  Future<bool> initialize({
    required void Function(String status) onStatus,
    required void Function(String error) onError,
  }) {
    return _stt.initialize(
      onStatus: onStatus,
      onError: (e) => onError(e.errorMsg),
    );
  }

  @override
  Future<List<String>> localeIds() async {
    final locales = await _stt.locales();
    return locales.map((l) => l.localeId).toList();
  }

  @override
  Future<void> listen({
    required String localeId,
    required void Function(String words, bool isFinal) onResult,
    required Duration pauseFor,
    required Duration listenFor,
  }) {
    return _stt.listen(
      onResult: (SpeechRecognitionResult r) =>
          onResult(r.recognizedWords, r.finalResult),
      listenOptions: stt.SpeechListenOptions(
        localeId: localeId,
        partialResults: true,
        listenMode: stt.ListenMode.dictation,
        pauseFor: pauseFor,
        listenFor: listenFor,
      ),
    );
  }

  @override
  Future<void> stop() => _stt.stop();
}

/// Real TTS backed by `flutter_tts`.
class PluginTtsEngine implements TtsEngine {
  final FlutterTts _tts = FlutterTts();

  @override
  Future<void> configure({
    required String languageTag,
    required double rate,
  }) async {
    await _tts.setLanguage(languageTag);
    await _tts.setSpeechRate(rate);
    // Make speak() resolve only when the utterance has actually finished, so
    // the caller can chain the next listen right after.
    await _tts.awaitSpeakCompletion(true);
  }

  @override
  Future<void> speak(String text) => _tts.speak(text);

  @override
  Future<void> stop() => _tts.stop();
}

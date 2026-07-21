import 'dart:async';

import 'speech_engines.dart';

/// Maps the learner's accent preference (profile: 'us' | 'uk') to the BCP-47
/// tag used for both recognition and synthesis. Unknown/absent -> US English.
String languageTagForAccent(String? accent) =>
    accent == 'uk' ? 'en-GB' : 'en-US';

/// On-device speech: recognition (STT) and synthesis (TTS). Free, no API keys —
/// the device/browser engines do the work. Abstracted so the ViewModel is
/// testable and so the timing behaviour can be unit-tested with fake engines.
abstract class SpeechService {
  Future<bool> initialize();

  /// Points recognition and synthesis at [languageTag] (BCP-47). Safe to call
  /// before or after [initialize]; a no-op when the tag is unchanged.
  Future<void> setLanguage(String languageTag);

  /// Listens for a single utterance and resolves with the recognized text
  /// (empty string if nothing was understood or an error occurred). [onPartial]
  /// receives interim words as they are recognised, for live on-screen feedback.
  Future<String> listenOnce({void Function(String words)? onPartial});

  Future<void> speak(String text);

  Future<void> stopListening();

  /// The last recognizer error reason (e.g. 'no-speech', 'network'), or null.
  String? get lastError;
}

/// On-device implementation over injectable [SttEngine]/[TtsEngine] ports.
///
/// IMPORTANT: the real STT plugin is a process-wide singleton whose status
/// callback binds ONCE. This service must therefore be a long-lived single
/// instance (see `speechServiceProvider`); language changes go through
/// [setLanguage], never through recreating it — a second instance would never
/// receive the singleton's status events and its [listenOnce] would hang.
class DeviceSpeechService implements SpeechService {
  DeviceSpeechService({
    SttEngine? stt,
    TtsEngine? tts,
    String languageTag = 'en-US',
  })  : _stt = stt ?? PluginSttEngine(),
        _tts = tts ?? PluginTtsEngine(),
        _languageTag = languageTag;

  /// TTS rate, slightly below default: a clearer model for a learner's ear.
  static const double kLearnerSpeechRate = 0.45;

  /// Trailing silence after which a turn is considered finished. Short enough
  /// that the learner is not left waiting, long enough not to cut mid-sentence.
  static const Duration kPauseFor = Duration(seconds: 2);

  /// Hard cap on a single utterance so a stuck recognizer cannot hang the turn.
  static const Duration kListenFor = Duration(seconds: 30);

  final SttEngine _stt;
  final TtsEngine _tts;

  String _languageTag;
  String get languageTag => _languageTag;

  bool _ready = false;
  // Resolved to a locale the recognizer actually supports (device locale IDs
  // vary: 'en-US' vs 'en_US'); falls back to [languageTag] when unknown.
  late String _sttLocaleId = _languageTag;

  Completer<String>? _turn;
  String _captured = '';
  void Function(String words)? _onPartial;

  String? _lastError;
  @override
  String? get lastError => _lastError;

  @override
  Future<bool> initialize() async {
    _ready = await _stt.initialize(onStatus: _onStatus, onError: _onError);
    if (_ready) {
      _sttLocaleId = await _resolveRecognitionLocale();
    }
    await _tts.configure(languageTag: _languageTag, rate: kLearnerSpeechRate);
    return _ready;
  }

  @override
  Future<void> setLanguage(String languageTag) async {
    if (languageTag == _languageTag) return;
    _languageTag = languageTag;
    _sttLocaleId = languageTag;
    if (_ready) {
      _sttLocaleId = await _resolveRecognitionLocale();
      await _tts.configure(languageTag: languageTag, rate: kLearnerSpeechRate);
    }
  }

  /// Picks the recognizer locale matching [languageTag]'s language (e.g. any
  /// `en*`), preferring an exact tag match. Falls back to [languageTag] when the
  /// device exposes no locales (common on web).
  Future<String> _resolveRecognitionLocale() async {
    final want = _normalize(_languageTag);
    final language = want.split('-').first;
    try {
      final ids = await _stt.localeIds();
      if (ids.isEmpty) return _languageTag;
      final sameLanguage =
          ids.where((id) => _normalize(id).split('-').first == language).toList();
      if (sameLanguage.isEmpty) return _languageTag;
      final exact = sameLanguage.where((id) => _normalize(id) == want);
      return exact.isNotEmpty ? exact.first : sameLanguage.first;
    } catch (_) {
      return _languageTag;
    }
  }

  static String _normalize(String localeId) =>
      localeId.toLowerCase().replaceAll('_', '-');

  void _onStatus(String status) {
    if ((status == 'done' || status == 'notListening')) {
      _completeTurn(_captured.trim());
    }
  }

  void _onError(String error) {
    _lastError = error;
    // Surface the failure by ending the turn empty instead of hanging forever.
    _completeTurn('');
  }

  void _completeTurn(String text) {
    if (_turn != null && !_turn!.isCompleted) {
      _turn!.complete(text);
    }
  }

  @override
  Future<String> listenOnce({void Function(String words)? onPartial}) async {
    if (!_ready) {
      await initialize();
      if (!_ready) return '';
    }
    // A previous turn may have ended via the status callback (or a timeout)
    // without the underlying recognizer actually being torn down — starting a
    // new session on top of it throws "recognition has already started" on web.
    // Always stop first so each turn begins from a clean state.
    await _stt.stop();

    _captured = '';
    _lastError = null;
    _onPartial = onPartial;
    _turn = Completer<String>();
    try {
      await _stt.listen(
        localeId: _sttLocaleId,
        pauseFor: kPauseFor,
        listenFor: kListenFor,
        onResult: (words, isFinal) {
          _captured = words;
          if (isFinal) {
            _completeTurn(words.trim());
          } else {
            _onPartial?.call(words);
          }
        },
      );
    } catch (e) {
      // Never leave the turn hanging: surface the reason and resolve empty.
      _lastError = e.toString();
      _completeTurn('');
    }
    return _turn!.future;
  }

  @override
  Future<void> speak(String text) => _tts.speak(text);

  @override
  Future<void> stopListening() => _stt.stop();
}

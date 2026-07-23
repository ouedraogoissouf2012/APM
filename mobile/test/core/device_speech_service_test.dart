import 'dart:async';

import 'package:apm/src/core/speech/speech_engines.dart';
import 'package:apm/src/core/speech/speech_service.dart';
import 'package:flutter_test/flutter_test.dart';

/// In-memory STT: the test drives what the recognizer "hears" and when it
/// finalises, so we can assert the service's behaviour without the plugin.
class _FakeStt implements SttEngine {
  _FakeStt({this.ready = true});

  final bool ready;
  final List<String> locales = const ['en-US', 'en_GB'];

  void Function(String status)? onStatus;
  void Function(String error)? onError;

  // Captured from the last listen() call.
  String? lastLocaleId;
  Duration? lastPauseFor;
  Duration? lastListenFor;
  int listenCalls = 0;
  int stopCalls = 0;
  bool stopped = false;

  // Mirrors the real web plugin: a session is "active" from listen() until
  // stop() (or a final result / status resets it). A second listen() while
  // active throws, exactly like SpeechRecognition.start does.
  bool _active = false;

  /// When set, the next [listen] throws it (models a plugin start failure).
  Object? throwOnNextListen;

  void Function(String words, bool isFinal)? _onResult;

  @override
  Future<bool> initialize({
    required void Function(String status) onStatus,
    required void Function(String error) onError,
  }) async {
    this.onStatus = onStatus;
    this.onError = onError;
    return ready;
  }

  @override
  Future<List<String>> localeIds() async => locales;

  @override
  Future<void> listen({
    required String localeId,
    required void Function(String words, bool isFinal) onResult,
    required Duration pauseFor,
    required Duration listenFor,
  }) async {
    final toThrow = throwOnNextListen;
    if (toThrow != null) {
      throwOnNextListen = null;
      throw toThrow;
    }
    if (_active) {
      throw StateError('recognition has already started');
    }
    _active = true;
    listenCalls++;
    lastLocaleId = localeId;
    lastPauseFor = pauseFor;
    lastListenFor = listenFor;
    _onResult = onResult;
  }

  @override
  Future<void> stop() async {
    stopCalls++;
    stopped = true;
    _active = false;
  }

  // Test helpers to simulate recognizer callbacks.
  void emitPartial(String words) => _onResult?.call(words, false);
  void emitFinal(String words) {
    _onResult?.call(words, true);
    _active = false; // the plugin ends the session on a final result
  }

  void fireError(String error) {
    onError?.call(error);
    _active = false; // errors also end the session
  }
}

class _FakeTts implements TtsEngine {
  String? spokenText;
  String? languageTag;
  double? rate;
  bool stopped = false;

  @override
  Future<void> configure({
    required String languageTag,
    required double rate,
  }) async {
    this.languageTag = languageTag;
    this.rate = rate;
  }

  @override
  Future<void> speak(String text) async {
    spokenText = text;
  }

  @override
  Future<void> stop() async {
    stopped = true;
  }
}

void main() {
  late _FakeStt stt;
  late _FakeTts tts;
  late DeviceSpeechService service;

  setUp(() {
    stt = _FakeStt();
    tts = _FakeTts();
    service = DeviceSpeechService(stt: stt, tts: tts);
  });

  group('initialize', () {
    test('returns true and configures TTS for the language', () async {
      final ready = await service.initialize();
      expect(ready, isTrue);
      expect(tts.languageTag, 'en-US');
      expect(tts.rate, DeviceSpeechService.kLearnerSpeechRate);
    });

    test('returns false when the recognizer is unavailable', () async {
      stt = _FakeStt(ready: false);
      service = DeviceSpeechService(stt: stt, tts: tts);
      expect(await service.initialize(), isFalse);
    });
  });

  group('listenOnce — reactivity', () {
    test('passes a bounded pauseFor so listening ends after the silence',
        () async {
      await service.initialize();
      unawaited(service.listenOnce());
      await Future<void>.value();

      expect(stt.lastPauseFor, DeviceSpeechService.kPauseFor);
      expect(stt.lastListenFor, DeviceSpeechService.kListenFor);
      expect(stt.lastPauseFor!.inSeconds, lessThanOrEqualTo(3));
    });

    test('resolves as soon as a final result arrives (no waiting on status)',
        () async {
      await service.initialize();
      final future = service.listenOnce();
      await Future<void>.value();

      stt.emitPartial('i went');
      stt.emitFinal('i went to the market');

      expect(await future, 'i went to the market');
    });

    test('resolves with the captured text when the status turns notListening',
        () async {
      await service.initialize();
      final future = service.listenOnce();
      await Future<void>.value();

      stt.emitPartial('hello there');
      stt.onStatus?.call('notListening');

      expect(await future, 'hello there');
    });

    test('a locale-matched id is passed to the recognizer', () async {
      await service.initialize();
      unawaited(service.listenOnce());
      await Future<void>.value();
      expect(stt.lastLocaleId, anyOf('en-US', 'en_US'));
    });

    test(
        'a second listenOnce right after a status-ended turn does not throw '
        '"already started" (stops the recognizer first)', () async {
      await service.initialize();

      // First turn ends via the status callback (notListening), which the web
      // plugin fires WITHOUT resetting the recognition object — the source of
      // the "recognition has already started" crash when chaining turns.
      final first = service.listenOnce();
      await Future<void>.value();
      stt.onStatus?.call('notListening');
      await first;

      // The loop immediately starts the next turn. This must not throw.
      final second = service.listenOnce();
      await Future<void>.value();
      stt.emitFinal('second turn');

      expect(await second, 'second turn');
      expect(stt.listenCalls, 2);
      // The service must have explicitly stopped between turns.
      expect(stt.stopCalls, greaterThanOrEqualTo(1));
    });
  });

  group('partial results feedback', () {
    test('streams interim words to the onPartial callback', () async {
      await service.initialize();
      final partials = <String>[];
      final future = service.listenOnce(onPartial: partials.add);
      await Future<void>.value();

      stt.emitPartial('i');
      stt.emitPartial('i went');
      stt.emitFinal('i went home');

      await future;
      expect(partials, ['i', 'i went']);
    });
  });

  group('errors are surfaced, not swallowed', () {
    test('a recognizer error resolves the turn empty and exposes the reason',
        () async {
      await service.initialize();
      final future = service.listenOnce();
      await Future<void>.value();

      stt.fireError('no-speech');

      expect(await future, '');
      expect(service.lastError, 'no-speech');
    });

    test('a listen() that throws surfaces a stable code, not a raw dump',
        () async {
      await service.initialize();
      stt.throwOnNextListen = StateError('recognition has already started');

      final text = await service.listenOnce();

      expect(text, '');
      // The UI keys messages off this value: it must be a stable reason code,
      // never a Dart exception's toString() (which leaks internals and is
      // impossible to branch on).
      expect(service.lastError, isNotNull);
      expect(service.lastError, isNot(contains('Instance of')));
      expect(service.lastError, isNot(contains('StateError')));
      expect(service.lastError, SpeechErrors.recognizerBusy);
    });
  });

  group('speak', () {
    test('delegates to the TTS engine', () async {
      await service.initialize();
      await service.speak('Nice to meet you');
      expect(tts.spokenText, 'Nice to meet you');
    });
  });
}

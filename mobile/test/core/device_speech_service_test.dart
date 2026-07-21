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
  bool stopped = false;

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
    listenCalls++;
    lastLocaleId = localeId;
    lastPauseFor = pauseFor;
    lastListenFor = listenFor;
    _onResult = onResult;
  }

  @override
  Future<void> stop() async {
    stopped = true;
  }

  // Test helpers to simulate recognizer callbacks.
  void emitPartial(String words) => _onResult?.call(words, false);
  void emitFinal(String words) => _onResult?.call(words, true);
  void fireError(String error) => onError?.call(error);
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
  });

  group('speak', () {
    test('delegates to the TTS engine', () async {
      await service.initialize();
      await service.speak('Nice to meet you');
      expect(tts.spokenText, 'Nice to meet you');
    });
  });
}

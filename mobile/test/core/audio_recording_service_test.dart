import 'dart:async';
import 'dart:typed_data';

import 'package:apm/src/core/audio/audio_recording_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:record/record.dart';

/// Reads a little-endian ASCII tag / integer out of a WAV header, so the tests
/// assert the real bytes rather than trusting the writer.
String _ascii(Uint8List b, int offset, int len) =>
    String.fromCharCodes(b.sublist(offset, offset + len));
int _u32(Uint8List b, int o) =>
    b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24);
int _u16(Uint8List b, int o) => b[o] | (b[o + 1] << 8);

/// A fake recorder that lets a test drive the chunk stream and its close, so the
/// accumulate/drain/stop cycle is deterministic without a microphone (#189).
class _FakeRecorder implements PcmRecorder {
  StreamController<Uint8List>? _current;
  bool permission = true;
  bool throwOnStart = false;
  int startCalls = 0;
  int stopCalls = 0;
  int cancelCalls = 0;

  @override
  Future<bool> hasPermission() async => permission;

  @override
  Future<Stream<Uint8List>> startStream(RecordConfig config) async {
    startCalls++;
    if (throwOnStart) throw StateError('start failed');
    final c = StreamController<Uint8List>();
    _current = c;
    return c.stream;
  }

  @override
  Future<void> stop() async {
    stopCalls++;
    await _current?.close(); // closes the stream -> service's onDone fires
  }

  @override
  Future<void> cancel() async => cancelCalls++;

  void emit(List<int> bytes) => _current?.add(Uint8List.fromList(bytes));
}

/// A controllable stand-in for [Timer] so tests can fire the duration bound
/// deterministically instead of waiting the real 60 s (#226).
class _FakeTimer implements Timer {
  _FakeTimer(this._callback);

  final void Function() _callback;
  bool cancelled = false;
  bool _fired = false;

  /// Simulates the timer elapsing. A no-op once cancelled or already fired,
  /// matching a real [Timer]'s behaviour.
  void fire() {
    if (cancelled || _fired) return;
    _fired = true;
    _callback();
  }

  @override
  void cancel() => cancelled = true;

  @override
  bool get isActive => !cancelled && !_fired;

  @override
  int get tick => 0;
}

/// Captures every [_FakeTimer] created via [factory], so a test can grab the
/// most recent one and drive it (`.fire()`) or assert it was cancelled.
class _TimerSpy {
  final List<_FakeTimer> created = [];

  Timer Function(Duration duration, void Function() callback) get factory =>
      (duration, callback) {
        final timer = _FakeTimer(callback);
        created.add(timer);
        return timer;
      };
}

const _headerLen = 44;

void main() {
  group('wrapPcmInWav', () {
    final pcm = Uint8List.fromList(List<int>.generate(1000, (i) => i % 256));

    test('produces a valid RIFF/WAVE container around the PCM payload', () {
      final wav = wrapPcmInWav(pcm, sampleRate: 16000, numChannels: 1);

      expect(_ascii(wav, 0, 4), 'RIFF');
      expect(_ascii(wav, 8, 4), 'WAVE');
      expect(_ascii(wav, 12, 4), 'fmt ');
      expect(_ascii(wav, 36, 4), 'data');
      // Header is 44 bytes; total length = header + payload.
      expect(wav.length, 44 + pcm.length);
    });

    test('header sizes match the payload exactly (no truncation)', () {
      final wav = wrapPcmInWav(pcm, sampleRate: 16000, numChannels: 1);

      // RIFF size = everything after the first 8 bytes.
      expect(_u32(wav, 4), 36 + pcm.length);
      // data size = the payload length precisely — the field Whisper reads to
      // know how much audio to decode. A wrong value here is the truncation bug.
      expect(_u32(wav, 40), pcm.length);
    });

    test('encodes the declared PCM format (mono, 16 kHz, 16-bit)', () {
      final wav = wrapPcmInWav(pcm, sampleRate: 16000, numChannels: 1);

      expect(_u16(wav, 20), 1); // PCM
      expect(_u16(wav, 22), 1); // mono
      expect(_u32(wav, 24), 16000); // sample rate
      expect(_u16(wav, 34), 16); // bits per sample
      expect(_u32(wav, 28), 16000 * 1 * 16 ~/ 8); // byte rate
      expect(_u16(wav, 32), 1 * 16 ~/ 8); // block align
    });

    test('appends the PCM bytes unchanged after the header', () {
      final wav = wrapPcmInWav(pcm, sampleRate: 16000, numChannels: 1);
      expect(wav.sublist(44), pcm);
    });

    test('honours stereo / other sample rates', () {
      final wav = wrapPcmInWav(pcm, sampleRate: 44100, numChannels: 2);
      expect(_u16(wav, 22), 2);
      expect(_u32(wav, 24), 44100);
      expect(_u32(wav, 28), 44100 * 2 * 16 ~/ 8);
      expect(_u16(wav, 32), 2 * 16 ~/ 8);
    });
  });

  group('DeviceAudioRecordingService', () {
    late _FakeRecorder recorder;
    late DeviceAudioRecordingService service;

    setUp(() {
      recorder = _FakeRecorder();
      service = DeviceAudioRecordingService(recorder: recorder);
    });

    test('accumulates every chunk and wraps them in a WAV', () async {
      expect(await service.start(), isTrue);
      recorder.emit([1, 2]);
      recorder.emit([3, 4, 5]);

      final wav = await service.stop();

      expect(wav, isNotNull);
      expect(wav!.length, _headerLen + 5);
      expect(wav.sublist(_headerLen), [1, 2, 3, 4, 5]); // nothing lost
    });

    test('captures the final buffer emitted just before stop (no truncation)', () async {
      await service.start();
      recorder.emit([9, 9]);
      // stop() closes the stream; the drain must deliver the in-flight buffer
      // before reading, so this chunk is present rather than dropped at the plugin
      // boundary.
      final wav = await service.stop();

      expect(wav!.sublist(_headerLen), [9, 9]);
    });

    test('a second start tears down the first take (re-entrant, no orphan)', () async {
      await service.start();
      recorder.emit([1]); // belongs to the abandoned first take
      await service.start(); // must discard the first take's buffer + subscription
      recorder.emit([2]);

      final wav = await service.stop();

      expect(recorder.startCalls, 2);
      expect(wav!.sublist(_headerLen), [2]); // only the second take survives
    });

    test('startStream failure returns false and leaves no half-open state', () async {
      recorder.throwOnStart = true;
      expect(await service.start(), isFalse);
      // No dangling subscription/buffer: a following stop() is a clean no-op.
      expect(await service.stop(), isNull);
    });

    test('denied microphone permission returns false', () async {
      recorder.permission = false;
      expect(await service.start(), isFalse);
    });

    test('stop without an active recording returns null', () async {
      expect(await service.stop(), isNull);
    });

    test('an empty capture (no chunks) returns null', () async {
      await service.start();
      expect(await service.stop(), isNull);
    });

    test('cancel tears down and forwards to the recorder', () async {
      await service.start();
      recorder.emit([7]);
      await service.cancel();

      expect(recorder.cancelCalls, 1);
      // After cancel, stop() has nothing to return.
      expect(await service.stop(), isNull);
    });
  });

  group('DeviceAudioRecordingService bounds (#226)', () {
    // RecordConfig has no native duration/size limit, so an utterance that
    // never gets explicitly stopped would otherwise grow RAM and on-device
    // storage without limit.
    late _FakeRecorder recorder;
    late _TimerSpy timers;

    setUp(() {
      recorder = _FakeRecorder();
      timers = _TimerSpy();
    });

    test(
      'the duration bound auto-stops capture, but a later stop() still '
      'returns everything buffered',
      () async {
        final service = DeviceAudioRecordingService(
          recorder: recorder,
          createTimer: timers.factory,
        );
        expect(await service.start(), isTrue);
        recorder.emit([1, 2, 3]);
        await pumpEventQueue();

        // Simulate the duration timer elapsing — no real 60 s wait.
        timers.created.single.fire();
        await pumpEventQueue();
        expect(recorder.stopCalls, 1); // capture stopped by the bound...

        // ...yet the learner's LATER explicit stop() still returns the take,
        // and does not stop the recorder a second time.
        final wav = await service.stop();
        expect(wav, isNotNull);
        expect(wav!.sublist(_headerLen), [1, 2, 3]);
        expect(recorder.stopCalls, 1);
      },
    );

    test('the byte bound auto-stops capture once exceeded', () async {
      final service = DeviceAudioRecordingService(
        recorder: recorder,
        maxBytes: 4,
        createTimer: timers.factory,
      );
      expect(await service.start(), isTrue);

      recorder.emit([1, 2]); // 2 bytes: under the 4-byte cap
      await pumpEventQueue();
      expect(recorder.stopCalls, 0);

      recorder.emit([3, 4, 5]); // 5 bytes total: over the cap -> auto-stop
      await pumpEventQueue();
      expect(recorder.stopCalls, 1);

      final wav = await service.stop();
      expect(wav!.sublist(_headerLen), [1, 2, 3, 4, 5]); // nothing lost
      expect(recorder.stopCalls, 1); // not stopped twice
    });

    test('a normal short take is unaffected by either bound', () async {
      final service = DeviceAudioRecordingService(
        recorder: recorder,
        createTimer: timers.factory,
      );
      expect(await service.start(), isTrue);
      recorder.emit([1, 2]);
      await pumpEventQueue();

      final wav = await service.stop();

      expect(wav!.sublist(_headerLen), [1, 2]);
      expect(recorder.stopCalls, 1);
      // The pending duration timer was cancelled by the normal stop(), not
      // left dangling.
      expect(timers.created.single.cancelled, isTrue);
    });

    test('cancel() also cancels the pending duration timer', () async {
      final service = DeviceAudioRecordingService(
        recorder: recorder,
        createTimer: timers.factory,
      );
      await service.start();

      await service.cancel();

      expect(timers.created.single.cancelled, isTrue);
    });

    test('a fired duration timer does not fire again after normal stop()',
        () async {
      // Guards the _autoStopping/_reset lifecycle across takes: a timer that
      // outlives its take (it shouldn't, but defensively) must not affect the
      // NEXT take's recorder.stopCalls count.
      final service = DeviceAudioRecordingService(
        recorder: recorder,
        createTimer: timers.factory,
      );
      await service.start();
      recorder.emit([1]);
      await service.stop();
      final firstTimer = timers.created.single;

      expect(firstTimer.cancelled, isTrue);
      firstTimer.fire(); // a no-op: cancelled timers don't fire
      expect(recorder.stopCalls, 1); // unaffected by the stray fire
    });
  });
}

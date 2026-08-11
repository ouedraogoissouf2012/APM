import 'dart:async';
import 'dart:typed_data';

import 'package:record/record.dart';

/// Records the learner's microphone to audio bytes, so the backend can
/// transcribe them with a real STT (Whisper via Groq) instead of the weak
/// on-device browser recognizer. Abstracted for testing.
abstract class AudioRecordingService {
  /// Starts recording; returns false if the microphone is unavailable.
  Future<bool> start();

  /// Stops recording and returns the captured audio bytes (null if nothing).
  Future<Uint8List?> stop();

  Future<void> cancel();
}

/// A minimal seam over the `record` plugin — just the four operations the capture
/// cycle uses. Injecting this (instead of the concrete [AudioRecorder]) makes the
/// accumulate/stop logic unit-testable with a fake that emits controlled chunks
/// and closes the stream on demand — no microphone, no platform channel.
abstract class PcmRecorder {
  Future<bool> hasPermission();
  Future<Stream<Uint8List>> startStream(RecordConfig config);
  Future<void> stop();
  Future<void> cancel();
}

/// Adapter binding [PcmRecorder] to the real plugin.
class RecordPcmRecorder implements PcmRecorder {
  RecordPcmRecorder([AudioRecorder? recorder]) : _recorder = recorder ?? AudioRecorder();

  final AudioRecorder _recorder;

  @override
  Future<bool> hasPermission() => _recorder.hasPermission();

  @override
  Future<Stream<Uint8List>> startStream(RecordConfig config) => _recorder.startStream(config);

  @override
  Future<void> stop() => _recorder.stop();

  @override
  Future<void> cancel() => _recorder.cancel();
}

/// Streams raw PCM chunks from the mic and assembles them into a WAV in memory.
///
/// WHY streaming instead of the recorder's file mode: on web, `record`'s WAV
/// file encoder accumulates the whole take inside a single AudioWorklet-fed blob
/// that some Chromium builds stop feeding after ~2-3 s — the returned WAV is
/// valid but silently truncated to the first couple of seconds, so a learner's
/// sentence is cut in half. Consuming the chunk STREAM and appending every chunk
/// ourselves removes that dependency: whatever the mic emits is captured until we
/// stop. We then wrap the accumulated PCM in a WAV header we control (mono 16 kHz,
/// exactly what Whisper wants), which is also smaller and faster to upload.
class DeviceAudioRecordingService implements AudioRecordingService {
  DeviceAudioRecordingService({
    PcmRecorder? recorder,
    Duration maxDuration = _defaultMaxDuration,
    int maxBytes = _defaultMaxBytes,
    Timer Function(Duration duration, void Function() callback)? createTimer,
  })  : _recorder = recorder ?? RecordPcmRecorder(),
        _maxDuration = maxDuration,
        _maxBytes = maxBytes,
        _createTimer = createTimer ?? Timer.new;

  final PcmRecorder _recorder;
  final Duration _maxDuration;
  final int _maxBytes;
  final Timer Function(Duration duration, void Function() callback) _createTimer;

  // Whisper is trained on 16 kHz mono; asking for it here avoids a needless
  // stereo/44.1 kHz capture (4x the bytes) and any resampling on the backend.
  static const int _sampleRate = 16000;
  static const int _numChannels = 1;
  // Upper bound on how long stop() waits for the stream to finish flushing before
  // giving up — so a stream that never closes cannot hang the UI.
  static const Duration _drainTimeout = Duration(seconds: 2);
  // Bounds on a single take (#226): RecordConfig has no native duration/size
  // limit, so an utterance that never gets stopped (a stuck UI, a background
  // app left recording) would otherwise grow RAM and on-device storage
  // without limit. A conversational turn never legitimately needs anywhere
  // near either bound.
  static const Duration _defaultMaxDuration = Duration(seconds: 60);
  // 16 kHz * 16-bit mono = 32,000 bytes/s: a 60 s take is ~1.9 MB. This is a
  // backstop independent of the duration timer (e.g. if the app is suspended
  // and timers are paused but the mic keeps buffering), so it is sized well
  // above what the duration cap alone would ever accumulate.
  static const int _defaultMaxBytes = 4 * 1024 * 1024;

  StreamSubscription<Uint8List>? _sub;
  BytesBuilder? _pcm;
  int _bytesSoFar = 0;
  // Completes when the chunk stream closes (after the recorder stops), so stop()
  // can wait for the last in-flight buffers instead of dropping them.
  Completer<void>? _closed;
  Timer? _boundTimer;
  // True once EITHER bound has triggered an internal stop — guards against
  // calling the underlying recorder's stop() twice (once from the bound,
  // once from an explicit stop()) for a single take.
  bool _autoStopping = false;

  @override
  Future<bool> start() async {
    // Re-entrant safe: tear down any prior take first, so a second start() cannot
    // orphan a live subscription or leak the previous PCM buffer.
    await _teardown();
    if (!await _recorder.hasPermission()) return false;
    final Stream<Uint8List> stream;
    try {
      stream = await _recorder.startStream(
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits,
          sampleRate: _sampleRate,
          numChannels: _numChannels,
        ),
      );
    } catch (_) {
      // Failure leaves NO half-open state (_pcm/_sub/_closed stay null).
      return false;
    }
    final pcm = BytesBuilder(copy: false);
    final closed = Completer<void>();
    _pcm = pcm;
    _closed = closed;
    _bytesSoFar = 0;
    _autoStopping = false;
    // Append every chunk as it arrives; complete `closed` when the stream ends so
    // stop() can drain the tail. A chunk that pushes the take past the byte bound
    // stops the underlying capture immediately (#226) — bytes already buffered
    // are still returned by the next stop() call.
    _sub = stream.listen(
      (chunk) {
        pcm.add(chunk);
        _bytesSoFar += chunk.length;
        if (_bytesSoFar >= _maxBytes) unawaited(_autoStop());
      },
      onDone: () {
        if (!closed.isCompleted) closed.complete();
      },
      cancelOnError: false,
    );
    _boundTimer = _createTimer(_maxDuration, () => unawaited(_autoStop()));
    return true;
  }

  /// Stops the underlying capture once, without discarding the buffered PCM —
  /// a later explicit [stop] still returns everything captured up to this
  /// point (#226). Safe to call more than once (e.g. both bounds firing).
  Future<void> _autoStop() async {
    if (_autoStopping || _sub == null) return;
    _autoStopping = true;
    await _recorder.stop();
  }

  @override
  Future<Uint8List?> stop() async {
    final sub = _sub;
    if (sub == null) return null;
    if (!_autoStopping) {
      _autoStopping = true;
      await _recorder.stop();
    }
    // Drain: the recorder.stop() closes the stream, but the final buffer(s) may
    // still be in flight. Wait for the stream's onDone before reading — otherwise
    // the last ~1 buffer at the plugin boundary is dropped and the sentence is cut
    // short. Bounded by _drainTimeout so a stream that never closes can't hang.
    final closed = _closed;
    if (closed != null && !closed.isCompleted) {
      await closed.future.timeout(_drainTimeout, onTimeout: () {});
    }
    await sub.cancel();
    _boundTimer?.cancel();
    final pcm = _pcm?.takeBytes();
    _reset();
    if (pcm == null || pcm.isEmpty) return null;
    return wrapPcmInWav(pcm, sampleRate: _sampleRate, numChannels: _numChannels);
  }

  @override
  Future<void> cancel() async {
    await _teardown();
    await _recorder.cancel();
  }

  Future<void> _teardown() async {
    _boundTimer?.cancel();
    await _sub?.cancel();
    _reset();
  }

  void _reset() {
    _sub = null;
    _pcm = null;
    _closed = null;
    _boundTimer = null;
    _bytesSoFar = 0;
    _autoStopping = false;
  }
}

/// Prepends a 44-byte WAV/PCM header to raw 16-bit PCM samples, producing a
/// self-describing container Whisper accepts and browsers can replay. Top-level
/// and pure so it is unit-testable without a microphone.
Uint8List wrapPcmInWav(
  Uint8List pcm, {
  required int sampleRate,
  required int numChannels,
}) {
  const bitsPerSample = 16;
  final byteRate = sampleRate * numChannels * bitsPerSample ~/ 8;
  final blockAlign = numChannels * bitsPerSample ~/ 8;
  final dataSize = pcm.length;
  final header = ByteData(44);
  // RIFF chunk descriptor
  _writeAscii(header, 0, 'RIFF');
  header.setUint32(4, 36 + dataSize, Endian.little); // chunk size
  _writeAscii(header, 8, 'WAVE');
  // fmt sub-chunk
  _writeAscii(header, 12, 'fmt ');
  header.setUint32(16, 16, Endian.little); // sub-chunk size (PCM)
  header.setUint16(20, 1, Endian.little); // audio format = PCM
  header.setUint16(22, numChannels, Endian.little);
  header.setUint32(24, sampleRate, Endian.little);
  header.setUint32(28, byteRate, Endian.little);
  header.setUint16(32, blockAlign, Endian.little);
  header.setUint16(34, bitsPerSample, Endian.little);
  // data sub-chunk
  _writeAscii(header, 36, 'data');
  header.setUint32(40, dataSize, Endian.little);

  final out = Uint8List(44 + dataSize);
  out.setRange(0, 44, header.buffer.asUint8List());
  out.setRange(44, 44 + dataSize, pcm);
  return out;
}

void _writeAscii(ByteData d, int offset, String s) {
  for (var i = 0; i < s.length; i++) {
    d.setUint8(offset + i, s.codeUnitAt(i));
  }
}

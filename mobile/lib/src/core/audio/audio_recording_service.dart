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
  DeviceAudioRecordingService({AudioRecorder? recorder})
      : _recorder = recorder ?? AudioRecorder();

  final AudioRecorder _recorder;

  // Whisper is trained on 16 kHz mono; asking for it here avoids a needless
  // stereo/44.1 kHz capture (4x the bytes) and any resampling on the backend.
  static const int _sampleRate = 16000;
  static const int _numChannels = 1;

  StreamSubscription<Uint8List>? _sub;
  BytesBuilder? _pcm;

  @override
  Future<bool> start() async {
    if (!await _recorder.hasPermission()) return false;
    _pcm = BytesBuilder(copy: false);
    final stream = await _recorder.startStream(
      const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: _sampleRate,
        numChannels: _numChannels,
      ),
    );
    // Append every chunk as it arrives — nothing is buffered inside the plugin
    // waiting to be flushed, so a long utterance cannot be truncated.
    _sub = stream.listen(
      (chunk) => _pcm?.add(chunk),
      cancelOnError: false,
    );
    return true;
  }

  @override
  Future<Uint8List?> stop() async {
    await _recorder.stop();
    // The stream closes on stop; give any in-flight chunk a chance to be
    // delivered before we read the accumulated bytes, then tear down.
    await _sub?.cancel();
    _sub = null;
    final pcm = _pcm?.takeBytes();
    _pcm = null;
    if (pcm == null || pcm.isEmpty) return null;
    return wrapPcmInWav(pcm, sampleRate: _sampleRate, numChannels: _numChannels);
  }

  @override
  Future<void> cancel() async {
    await _sub?.cancel();
    _sub = null;
    _pcm = null;
    await _recorder.cancel();
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

import 'dart:typed_data';

import 'package:dio/dio.dart';
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

class DeviceAudioRecordingService implements AudioRecordingService {
  final AudioRecorder _recorder = AudioRecorder();

  @override
  Future<bool> start() async {
    if (!await _recorder.hasPermission()) return false;
    // Opus in a WebM container: recorded natively by the browser and accepted
    // by Whisper. `path` is ignored on web (records to an in-memory blob).
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.opus),
      path: 'speech.webm',
    );
    return true;
  }

  @override
  Future<Uint8List?> stop() async {
    final location = await _recorder.stop();
    if (location == null) return null;
    // On web `location` is a blob: URL; on native it is a file path. Dio reads
    // both as bytes (the browser resolves blob: URLs).
    try {
      final resp = await Dio().get<List<int>>(
        location,
        options: Options(responseType: ResponseType.bytes),
      );
      final data = resp.data;
      return (data == null || data.isEmpty) ? null : Uint8List.fromList(data);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> cancel() => _recorder.cancel();
}

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'audio_playback_service.dart';
import 'audio_recording_service.dart';

/// Audio infrastructure providers live in core so any feature (conversation,
/// echo, ...) depends on core instead of importing another feature's view model
/// for plumbing. Tests override these by name.
final audioPlaybackProvider = Provider<AudioPlaybackService>(
  (ref) => DeviceAudioPlaybackService(),
);

final audioRecordingProvider = Provider<AudioRecordingService>(
  (ref) => DeviceAudioRecordingService(),
);

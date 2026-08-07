import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'audio_playback_service.dart';
import 'audio_recording_service.dart';
import 'voice_take_store.dart';

/// Audio infrastructure providers live in core so any feature (conversation,
/// echo, ...) depends on core instead of importing another feature's view model
/// for plumbing. Tests override these by name.
final audioPlaybackProvider = Provider<AudioPlaybackService>(
  (ref) => DeviceAudioPlaybackService(),
);

final audioRecordingProvider = Provider<AudioRecordingService>(
  (ref) => DeviceAudioRecordingService(),
);

/// On-device store of the learner's spoken takes, for the audible before/after
/// proof (#199). Single instance per app run (in-memory for now).
final voiceTakeStoreProvider = Provider<VoiceTakeStore>(
  (ref) => InMemoryVoiceTakeStore(),
);

/// The baseline + latest takes for a skill (null until there are two to compare).
final voiceTakesProvider = FutureProvider.family<VoiceTakes?, String>(
  (ref, skill) => ref.watch(voiceTakeStoreProvider).takesFor(skill),
);

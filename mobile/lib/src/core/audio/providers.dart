import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'audio_playback_service.dart';
import 'audio_recording_service.dart';
import 'voice_take_store.dart';
// Native persists takes to files; web falls back to in-memory (chosen at compile
// time by the presence of dart:io).
import 'persistent_voice_take_store.dart'
    if (dart.library.io) 'persistent_voice_take_store_io.dart';

/// Audio infrastructure providers live in core so any feature (conversation,
/// echo, ...) depends on core instead of importing another feature's view model
/// for plumbing. Tests override these by name.
final audioPlaybackProvider = Provider<AudioPlaybackService>(
  (ref) {
    final service = DeviceAudioPlaybackService();
    ref.onDispose(service.dispose);
    return service;
  },
);

final audioRecordingProvider = Provider<AudioRecordingService>(
  (ref) => DeviceAudioRecordingService(),
);

/// On-device store of the learner's spoken takes, for the audible before/after
/// proof (#199). Persistent (files) on native so the before/after survives a
/// restart; in-memory on web (tracked debt). Single instance per app run.
final voiceTakeStoreProvider = Provider<VoiceTakeStore>(
  (ref) => createVoiceTakeStore(),
);

/// The baseline + latest takes for a skill (null until there are two to compare).
final voiceTakesProvider = FutureProvider.family<VoiceTakes?, String>(
  (ref, skill) => ref.watch(voiceTakeStoreProvider).takesFor(skill),
);

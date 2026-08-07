import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'file_voice_take_store.dart';
import 'voice_take_store.dart';

/// Native factory: persist the learner's takes as files under a dedicated folder
/// in the app documents directory, so the audible before/after survives restarts.
/// The directory is opened lazily (on first read/write) so the provider stays sync.
VoiceTakeStore createVoiceTakeStore() => FileVoiceTakeStore(
      () async => Directory('${(await getApplicationDocumentsDirectory()).path}/voice_takes'),
    );

import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'encrypted_voice_take_store.dart';
import 'file_voice_take_store.dart';
import 'ttl_voice_take_store.dart';
import 'voice_take_store.dart';

/// Native factory: persist the learner's takes as files under a dedicated folder
/// in the app documents directory, so the audible before/after survives restarts.
/// The directory is opened lazily (on first read/write) so the provider stays sync.
///
/// Wrapped in [EncryptedVoiceTakeStore] (#226): the file would otherwise hold
/// the raw audio in plaintext, readable on a stolen/shared device.
/// [TtlVoiceTakeStore] sits outermost so its retention bound (and physical
/// purge) applies uniformly whether or not the inner bytes happen to be
/// encrypted.
VoiceTakeStore createVoiceTakeStore() => TtlVoiceTakeStore(
      EncryptedVoiceTakeStore(
        FileVoiceTakeStore(
          () async => Directory('${(await getApplicationDocumentsDirectory()).path}/voice_takes'),
        ),
      ),
    );

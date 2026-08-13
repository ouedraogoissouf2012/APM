import 'dart:async';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'encrypted_voice_take_store.dart';
import 'file_voice_take_store.dart';
import 'ttl_voice_take_store.dart';
import 'user_scoped_voice_take_store.dart';
import 'voice_take_store.dart';

/// Native factory: persist the learner's takes as files under a dedicated folder
/// in the app documents directory, so the audible before/after survives restarts.
/// The directory is opened lazily (on first read/write) so the provider stays sync.
///
/// Wrapped in [EncryptedVoiceTakeStore] (#226): the file would otherwise hold
/// the raw audio in plaintext, readable on a stolen/shared device.
/// [TtlVoiceTakeStore] sits outermost of those so its retention bound (and
/// physical purge) applies uniformly whether or not the inner bytes happen to
/// be encrypted, and [UserScopedVoiceTakeStore] sits outermost of ALL of them
/// (#319) so every key this whole chain ever sees is already scoped to the
/// signed-in user.
VoiceTakeStore createVoiceTakeStore() {
  final ttl = TtlVoiceTakeStore(
    EncryptedVoiceTakeStore(
      FileVoiceTakeStore(
        () async => Directory('${(await getApplicationDocumentsDirectory()).path}/voice_takes'),
      ),
    ),
  );
  // Startup sweep (#321): fire-and-forget, best-effort — a sweep failure
  // must never block app startup, and there's nowhere here to report it
  // (this is a plain factory, no crash-reporter Ref available).
  unawaited(ttl.sweepExpired().catchError((_) {}));
  return UserScopedVoiceTakeStore(ttl);
}

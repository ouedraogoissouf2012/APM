import 'dart:async';

import 'encrypted_voice_take_store.dart';
import 'indexed_db_voice_take_kv.dart';
import 'kv_voice_take_store.dart';
import 'ttl_voice_take_store.dart';
import 'user_scoped_voice_take_store.dart';
import 'voice_take_store.dart';

/// Default / web factory. The web build now persists takes in IndexedDB (#205) so
/// the audible before/after survives a page reload — matching the native build,
/// which persists to files (chosen instead of this file by the conditional import
/// on `dart.library.io`).
///
/// Wrapped in [EncryptedVoiceTakeStore] (#226): IndexedDB otherwise holds the
/// raw audio in plaintext, readable via DevTools. [TtlVoiceTakeStore] sits
/// outermost of those so its retention bound (and physical purge) applies
/// uniformly whether or not the inner bytes happen to be encrypted, and
/// [UserScopedVoiceTakeStore] sits outermost of ALL of them (#319) so every
/// key this whole chain ever sees is already scoped to the signed-in user.
VoiceTakeStore createVoiceTakeStore() {
  final ttl = TtlVoiceTakeStore(
    EncryptedVoiceTakeStore(KvVoiceTakeStore(IndexedDbVoiceTakeKv())),
  );
  // Startup sweep (#321): fire-and-forget, best-effort — a sweep failure
  // must never block app startup, and there's nowhere here to report it
  // (this is a plain factory, no crash-reporter Ref available).
  unawaited(ttl.sweepExpired().catchError((_) {}));
  return UserScopedVoiceTakeStore(ttl);
}

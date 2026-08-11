import 'encrypted_voice_take_store.dart';
import 'indexed_db_voice_take_kv.dart';
import 'kv_voice_take_store.dart';
import 'ttl_voice_take_store.dart';
import 'voice_take_store.dart';

/// Default / web factory. The web build now persists takes in IndexedDB (#205) so
/// the audible before/after survives a page reload — matching the native build,
/// which persists to files (chosen instead of this file by the conditional import
/// on `dart.library.io`).
///
/// Wrapped in [EncryptedVoiceTakeStore] (#226): IndexedDB otherwise holds the
/// raw audio in plaintext, readable via DevTools. [TtlVoiceTakeStore] sits
/// outermost so its retention bound (and physical purge) applies uniformly
/// whether or not the inner bytes happen to be encrypted.
VoiceTakeStore createVoiceTakeStore() => TtlVoiceTakeStore(
      EncryptedVoiceTakeStore(KvVoiceTakeStore(IndexedDbVoiceTakeKv())),
    );

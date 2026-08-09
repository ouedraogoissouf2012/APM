import 'indexed_db_voice_take_kv.dart';
import 'kv_voice_take_store.dart';
import 'voice_take_store.dart';

/// Default / web factory. The web build now persists takes in IndexedDB (#205) so
/// the audible before/after survives a page reload — matching the native build,
/// which persists to files (chosen instead of this file by the conditional import
/// on `dart.library.io`).
VoiceTakeStore createVoiceTakeStore() =>
    KvVoiceTakeStore(IndexedDbVoiceTakeKv());

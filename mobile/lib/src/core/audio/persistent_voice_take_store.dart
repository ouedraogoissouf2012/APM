import 'voice_take_store.dart';

/// Default / web factory. The web build has no filesystem, so takes live for the
/// app run only. Persistent web storage (IndexedDB) is a tracked follow-up — the
/// native build (below, chosen by conditional import) already persists to files.
VoiceTakeStore createVoiceTakeStore() => InMemoryVoiceTakeStore();

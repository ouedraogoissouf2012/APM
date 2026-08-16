import 'voice_take_store.dart';

/// Web factory (#436). Persisting takes (even AES-GCM) is unsafe here: the
/// wrap key lives in localStorage (#318), so XSS/DevTools unwraps recordings.
/// Native still uses files + Keystore (see persistent_voice_take_store_io.dart).
/// Session tokens stay in flutter_secure_storage; httpOnly cookies are a
/// follow-up, not this issue.
VoiceTakeStore createVoiceTakeStore() => InMemoryVoiceTakeStore();

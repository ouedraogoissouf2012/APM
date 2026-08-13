import 'dart:typed_data';

import 'voice_take_store.dart';

/// A minimal async byte key-value store — the persistence seam beneath
/// [KvVoiceTakeStore].
///
/// Kept deliberately tiny so the platform layer (IndexedDB on web, #205) is a
/// thin, swappable adapter, while the take LOGIC above stays pure Dart and can be
/// unit-tested with an in-memory fake — the real IndexedDB cannot run on the Dart
/// VM, so the logic must not be trapped inside it.
abstract class VoiceTakeKvStore {
  /// The bytes stored at [key], or null if absent.
  Future<Uint8List?> read(String key);

  /// Stores [bytes] at [key], overwriting any previous value.
  Future<void> write(String key, Uint8List bytes);

  /// Removes the entry at [key], if any — the single-skill purge (#226).
  Future<void> delete(String key);

  /// Removes every entry — the on-device erase (#219).
  Future<void> clear();

  /// Every key currently present — used only by [KvVoiceTakeStore.knownSkills]
  /// for the startup TTL sweep (#321).
  Future<Set<String>> keys();
}

/// [VoiceTakeStore] implemented over a persistent [VoiceTakeKvStore], mirroring
/// the native file store: the FIRST take of a skill becomes the baseline (written
/// once), every take updates the latest, and a before/after is exposed only once
/// there are two DISTINCT takes.
///
/// Because the KV persists across app runs (IndexedDB on web), so does the audible
/// before/after — that persistence is the whole point of #205 (the previous web
/// fallback was in-memory and lost the "you, 7 days ago" comparison on reload).
class KvVoiceTakeStore implements VoiceTakeStore, SkillEnumerator {
  KvVoiceTakeStore(this._kv);

  final VoiceTakeKvStore _kv;

  @override
  Future<void> saveTake(String skill, Uint8List bytes) async {
    final key = _safe(skill);
    // Baseline is written once (first take); latest is written every time.
    if (await _kv.read('$key.baseline') == null) {
      await _kv.write('$key.baseline', bytes);
    }
    await _kv.write('$key.latest', bytes);
  }

  @override
  Future<VoiceTakes?> takesFor(String skill) async {
    final key = _safe(skill);
    final baseline = await _kv.read('$key.baseline');
    final latest = await _kv.read('$key.latest');
    if (baseline == null || latest == null) return null;
    // Two DISTINCT takes required: the first save leaves baseline == latest, so
    // there is no "after" to compare yet (mirrors the text proof's two-sessions
    // rule and the native file store).
    if (_equal(baseline, latest)) return null;
    return VoiceTakes(baseline: baseline, latest: latest);
  }

  @override
  Future<void> eraseAll() => _kv.clear();

  @override
  Future<void> deleteSkill(String skill) async {
    final key = _safe(skill);
    await _kv.delete('$key.baseline');
    await _kv.delete('$key.latest');
  }

  /// Returns SAFE-transformed stems (post-[_safe]) — see the equivalent note
  /// on [FileVoiceTakeStore.knownSkills]; round-trips correctly through
  /// [takesFor]/[deleteSkill] because [_safe] is idempotent on its own output.
  @override
  Future<Set<String>> knownSkills() async {
    final stems = <String>{};
    for (final key in await _kv.keys()) {
      if (key.endsWith('.baseline')) {
        stems.add(key.substring(0, key.length - '.baseline'.length));
      } else if (key.endsWith('.latest')) {
        stems.add(key.substring(0, key.length - '.latest'.length));
      }
    }
    return stems;
  }

  /// Skill -> a safe key stem (skills are scenario ids/slugs, but be defensive).
  static String _safe(String skill) => safeStorageKey(skill);

  static bool _equal(Uint8List a, Uint8List b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }
}

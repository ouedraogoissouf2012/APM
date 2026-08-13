import 'dart:typed_data';

/// The learner's two comparable spoken takes on a skill, for the AUDIBLE
/// before/after proof (#199): hear your first attempt, then your most recent one.
class VoiceTakes {
  const VoiceTakes({required this.baseline, required this.latest});

  final Uint8List baseline; // the first take captured on this skill
  final Uint8List latest; // the most recent take
}

/// On-device store of the learner's spoken takes per skill.
///
/// Kept behind a seam so the proof screen (and, later, the capture path) depend
/// on an interface, not a concrete store — swappable for a persistent
/// implementation without touching callers, and unit-testable with a fake.
///
/// Privacy (#128): these takes live ON THE DEVICE only. Raw learner audio is
/// never stored server-side, so the before/after A/B must be local.
abstract class VoiceTakeStore {
  /// Saves a take for [skill]. The FIRST take becomes the baseline; every later
  /// one updates the latest — so the store always exposes an honest before/after.
  Future<void> saveTake(String skill, Uint8List bytes);

  /// The baseline + latest takes for [skill], or null until there are TWO
  /// distinct takes to compare (mirrors the text proof's "need two sessions" rule).
  Future<VoiceTakes?> takesFor(String skill);

  /// Erases ALL local takes for every skill — the on-device half of "erase my
  /// voice data" (#219). The audible before/after lives ONLY on the device
  /// (#128), so a server-only delete would leave the raw audio behind and make
  /// the UI's "erased" claim a lie.
  Future<void> eraseAll();

  /// Physically removes whatever is stored for [skill] alone (#226): used by
  /// [TtlVoiceTakeStore] to purge bytes whose retention has expired and by
  /// [EncryptedVoiceTakeStore] to purge a take that no longer decrypts,
  /// without waiting for a full [eraseAll]. A no-op if nothing is stored for
  /// [skill].
  Future<void> deleteSkill(String skill);
}

/// Normalises a skill/storage key to the SAFE form [FileVoiceTakeStore] and
/// [KvVoiceTakeStore] use for filenames/KV keys — idempotent, so applying it
/// to an already-safe string is a no-op.
///
/// Shared (#320) so [EncryptedVoiceTakeStore] can derive its AES-GCM
/// associated data from a form that's IDENTICAL regardless of which of two
/// different strings a caller hands it for the SAME underlying take:
/// - A normal saveTake/takesFor is handed the raw key (e.g. `'7:job_interview'`
///   once #319's user-scoping prefixes it).
/// - [TtlVoiceTakeStore.sweepExpired] (#321) is handed the ALREADY-safe stem
///   [SkillEnumerator.knownSkills] returns (e.g. `'7_job_interview'` — the
///   file system only ever exposes the post-transform name back).
///
/// Without normalising the AAD input the same way in both cases, the two
/// paths would compute DIFFERENT associated data for the same physical take
/// whenever the raw key contains a character [safeStorageKey] rewrites —
/// which, since #319 always prefixes every key with `'$userId:'`, is now
/// EVERY key. GCM authentication would then fail on every sweep-triggered
/// read, and the (perfectly fresh) take would be wrongly treated as
/// undecryptable and physically purged — on every app restart.
String safeStorageKey(String raw) => raw.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');

/// Optional capability some [VoiceTakeStore]s expose: enumerating every
/// skill that currently has something stored. Kept OUT of [VoiceTakeStore]
/// itself — [VoiceTakeStore] is deliberately skill-keyed, not iterable, and
/// a couple of tests outside the audio-storage module implement it directly
/// as a plain interface (e.g. voice_privacy_screen_test.dart,
/// conversation_view_model_test.dart); adding a required method there would
/// break them. [TtlVoiceTakeStore.sweepExpired] (#321) uses this, when its
/// inner store happens to support it, to find takes to check without
/// needing them to be read first.
abstract class SkillEnumerator {
  Future<Set<String>> knownSkills();
}

/// In-memory store — takes live for the app run. A persistent on-device
/// implementation (so the before/after survives across days) is a follow-up
/// increment; kept behind [VoiceTakeStore] so that swap touches no caller.
class InMemoryVoiceTakeStore implements VoiceTakeStore, SkillEnumerator {
  final Map<String, Uint8List> _baseline = {};
  final Map<String, Uint8List> _latest = {};

  @override
  Future<void> saveTake(String skill, Uint8List bytes) async {
    _baseline.putIfAbsent(skill, () => bytes);
    _latest[skill] = bytes;
  }

  @override
  Future<VoiceTakes?> takesFor(String skill) async {
    final baseline = _baseline[skill];
    final latest = _latest[skill];
    // Need two DISTINCT takes: after a single save baseline and latest are the
    // same object, so there is no "after" to compare yet.
    if (baseline == null || latest == null || identical(baseline, latest)) {
      return null;
    }
    return VoiceTakes(baseline: baseline, latest: latest);
  }

  @override
  Future<void> eraseAll() async {
    _baseline.clear();
    _latest.clear();
  }

  @override
  Future<void> deleteSkill(String skill) async {
    _baseline.remove(skill);
    _latest.remove(skill);
  }

  @override
  Future<Set<String>> knownSkills() async => {..._baseline.keys, ..._latest.keys};
}

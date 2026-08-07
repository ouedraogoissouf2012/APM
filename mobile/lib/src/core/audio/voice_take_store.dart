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
}

/// In-memory store — takes live for the app run. A persistent on-device
/// implementation (so the before/after survives across days) is a follow-up
/// increment; kept behind [VoiceTakeStore] so that swap touches no caller.
class InMemoryVoiceTakeStore implements VoiceTakeStore {
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
}

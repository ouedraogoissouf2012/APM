import 'dart:typed_data';

import 'package:apm/src/core/audio/ttl_voice_take_store.dart';
import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:flutter_test/flutter_test.dart';

/// A raw in-memory [VoiceTakeStore] with NO timestamp semantics of its own —
/// stands in for whichever real store (file/IndexedDB) [TtlVoiceTakeStore]
/// wraps, so the wrapper's TTL logic is tested in isolation.
class _RawStore implements VoiceTakeStore {
  final Map<String, Uint8List> _baseline = {};
  final Map<String, Uint8List> _latest = {};
  int eraseAllCalls = 0;
  final List<String> deleteSkillCalls = [];

  @override
  Future<void> saveTake(String skill, Uint8List bytes) async {
    _baseline.putIfAbsent(skill, () => bytes);
    _latest[skill] = bytes;
  }

  @override
  Future<VoiceTakes?> takesFor(String skill) async {
    final baseline = _baseline[skill];
    final latest = _latest[skill];
    if (baseline == null || latest == null) return null;
    return VoiceTakes(baseline: baseline, latest: latest);
  }

  @override
  Future<void> eraseAll() async {
    eraseAllCalls++;
    _baseline.clear();
    _latest.clear();
  }

  @override
  Future<void> deleteSkill(String skill) async {
    deleteSkillCalls.add(skill);
    _baseline.remove(skill);
    _latest.remove(skill);
  }

  /// Test-only seam: overwrite exactly what the raw store holds, bypassing
  /// [TtlVoiceTakeStore]'s stamping — used to simulate a pre-#226 legacy
  /// payload with no timestamp header at all.
  void seedRaw(String skill, Uint8List baseline, Uint8List latest) {
    _baseline[skill] = baseline;
    _latest[skill] = latest;
  }

  /// Test-only seam: the exact bytes the wrapper delegated for [skill]'s
  /// baseline, bypassing any TTL stripping — lets a test confirm stamping
  /// happened without depending on the two-distinct-takes read rule.
  Uint8List? peekBaseline(String skill) => _baseline[skill];
}

void main() {
  group('TtlVoiceTakeStore', () {
    late _RawStore raw;
    late DateTime clock;
    late TtlVoiceTakeStore store;

    setUp(() {
      raw = _RawStore();
      clock = DateTime.utc(2026, 1, 1);
      store = TtlVoiceTakeStore(
        raw,
        ttl: const Duration(days: 30),
        now: () => clock,
      );
    });

    test('a fresh take is readable immediately after saving', () async {
      await store.saveTake('job_interview', Uint8List.fromList([1, 2, 3]));
      // A second, DISTINCT save so baseline != latest (mirrors the "two takes
      // needed for a before/after" rule the underlying stores already enforce).
      await store.saveTake('job_interview', Uint8List.fromList([4, 5, 6]));

      final takes = await store.takesFor('job_interview');

      expect(takes, isNotNull);
      expect(takes!.baseline, [1, 2, 3]);
      expect(takes.latest, [4, 5, 6]);
    });

    test('a take exactly at the TTL boundary is still readable', () async {
      await store.saveTake('a', Uint8List.fromList([1]));
      clock = clock.add(const Duration(days: 30));
      await store.saveTake('a', Uint8List.fromList([2]));

      // Baseline is now EXACTLY 30 days old (== ttl, not >). "> ttl" is what
      // expires a take, so the boundary itself is still fresh.
      final takes = await store.takesFor('a');
      expect(takes, isNotNull);
    });

    test('a take older than the TTL is treated as absent', () async {
      await store.saveTake('a', Uint8List.fromList([1]));
      clock = clock.add(const Duration(days: 30) + const Duration(seconds: 1));
      await store.saveTake('a', Uint8List.fromList([2]));
      // The BASELINE (saved at t=0) is now stale; latest (saved just now) is not.

      final takes = await store.takesFor('a');

      // Both required for a before/after — a stale baseline hides the pair,
      // even though latest alone is still fresh.
      expect(takes, isNull);
    });

    test('a stale take is PHYSICALLY purged from the inner store, not just '
        'hidden (#226)', () async {
      await store.saveTake('a', Uint8List.fromList([1]));
      clock = clock.add(const Duration(days: 30) + const Duration(seconds: 1));
      await store.saveTake('a', Uint8List.fromList([2]));

      await store.takesFor('a'); // the read that notices the staleness

      expect(raw.deleteSkillCalls, ['a']);
      expect(raw._baseline.containsKey('a'), isFalse);
      expect(raw._latest.containsKey('a'), isFalse);
    });

    test('a fresh take is NOT purged', () async {
      await store.saveTake('a', Uint8List.fromList([1]));
      await store.saveTake('a', Uint8List.fromList([2]));

      await store.takesFor('a');

      expect(raw.deleteSkillCalls, isEmpty);
    });

    test('after a stale take is purged, the next save starts a genuinely '
        'fresh baseline', () async {
      await store.saveTake('a', Uint8List.fromList([1]));
      clock = clock.add(const Duration(days: 30) + const Duration(seconds: 1));
      await store.saveTake('a', Uint8List.fromList([2]));
      await store.takesFor('a'); // triggers the physical purge

      await store.saveTake('a', Uint8List.fromList([9]));
      await store.saveTake('a', Uint8List.fromList([10]));

      final takes = await store.takesFor('a');
      expect(takes, isNotNull);
      expect(takes!.baseline, [9]); // NOT the stale [1]
    });

    test('a too-short legacy payload is treated as absent, not a crash',
        () async {
      // Shorter than the 8-byte header this wrapper expects.
      raw.seedRaw('a', Uint8List.fromList([1, 2]), Uint8List.fromList([3, 4]));

      final takes = await store.takesFor('a');

      expect(takes, isNull); // absent, not an exception
    });

    test('a realistic pre-#226 WAV payload (no timestamp header, but long '
        'enough to look like one) is treated as absent, not a crash',
        () async {
      // A real WAV starts with the ASCII bytes "RIFF...." — exactly what a
      // learner's take saved by a version of the app BEFORE this fix would
      // still have on disk. Misread as our 8-byte epoch-millis header, this
      // must degrade to "stale/absent", never throw.
      final legacyWav = Uint8List.fromList([
        0x52, 0x49, 0x46, 0x46, // "RIFF"
        0x24, 0x00, 0x00, 0x00, // chunk size
        0x57, 0x41, 0x56, 0x45, // "WAVE" — the rest of a real WAV header
      ]);
      raw.seedRaw('a', legacyWav, legacyWav);

      final takes = await store.takesFor('a');

      expect(takes, isNull); // absent, not an exception
    });

    test('saveTake delegates to the inner store with a timestamp header '
        'stamped on (not the original bytes verbatim)', () async {
      await store.saveTake('a', Uint8List.fromList([9, 9]));

      final storedBaseline = raw.peekBaseline('a');
      expect(storedBaseline, isNotNull);
      // 2 original bytes + the 8-byte epoch-millis header.
      expect(storedBaseline!.length, 10);
    });

    test('eraseAll forwards to the inner store', () async {
      await store.eraseAll();
      expect(raw.eraseAllCalls, 1);
    });

    test('deleteSkill forwards to the inner store', () async {
      await store.deleteSkill('a');
      expect(raw.deleteSkillCalls, ['a']);
    });
  });
}

import 'dart:async';
import 'dart:typed_data';

import 'package:apm/src/core/audio/user_scoped_voice_take_store.dart';
import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:apm/src/core/storage/key_value_store.dart';
import 'package:flutter_test/flutter_test.dart';

/// A raw in-memory [VoiceTakeStore] — stands in for whichever real chain
/// (Ttl/Encrypted/File/IndexedDB) [UserScopedVoiceTakeStore] wraps, exposing
/// the EXACT keys it was handed so a test can assert on the scoping.
class _RawStore implements VoiceTakeStore {
  final Map<String, Uint8List> baseline = {};
  final Map<String, Uint8List> latest = {};
  int eraseAllCalls = 0;
  Object? throwOnEraseAll;

  @override
  Future<void> saveTake(String skill, Uint8List bytes) async {
    baseline.putIfAbsent(skill, () => bytes);
    latest[skill] = bytes;
  }

  @override
  Future<VoiceTakes?> takesFor(String skill) async {
    final b = baseline[skill];
    final l = latest[skill];
    if (b == null || l == null || identical(b, l)) return null;
    return VoiceTakes(baseline: b, latest: l);
  }

  @override
  Future<void> eraseAll() async {
    eraseAllCalls++;
    final err = throwOnEraseAll;
    if (err != null) throw err;
    baseline.clear();
    latest.clear();
  }

  @override
  Future<void> deleteSkill(String skill) async {
    baseline.remove(skill);
    latest.remove(skill);
  }
}

class _InMemoryKeyValueStore implements KeyValueStore {
  final Map<String, String> _m = {};
  @override
  Future<String?> read(String key) async => _m[key];
  @override
  Future<void> write(String key, String value) async => _m[key] = value;
  @override
  Future<void> delete(String key) async => _m.remove(key);
}

/// Like [_InMemoryKeyValueStore], but [read] can be told to hang until
/// released — lets a test deterministically land a read in flight WHILE a
/// concurrent write resolves, instead of hoping for a timing coincidence.
class _DelayableReadKeyValueStore implements KeyValueStore {
  final Map<String, String> _m = {};
  Completer<void>? _armedGate; // consumed by the NEXT read call only (one-shot)
  Completer<void>? _activeGate; // what that read is actually awaiting

  /// The NEXT call to [read] will suspend until [releaseRead] is called.
  /// Only that one call blocks — a later, concurrent [read] proceeds
  /// immediately, exactly like a second unrelated caller racing in.
  void blockNextRead() => _armedGate = Completer<void>();

  void releaseRead() => _activeGate?.complete();

  @override
  Future<String?> read(String key) async {
    // Snapshot BEFORE the delay, not after — models a real read already in
    // flight to the OS/platform channel: its result is whatever existed
    // when it was DISPATCHED, not whatever a concurrent write lands later.
    // A live re-read of `_m` after the delay would trivially reflect the
    // concurrent write and defeat the whole point of this fake.
    final snapshot = _m[key];
    final armed = _armedGate;
    if (armed != null) {
      _armedGate = null;
      _activeGate = armed;
      await armed.future;
    }
    return snapshot;
  }

  @override
  Future<void> write(String key, String value) async => _m[key] = value;
  @override
  Future<void> delete(String key) async => _m.remove(key);
}

Uint8List _b(List<int> bytes) => Uint8List.fromList(bytes);

void main() {
  group('UserScopedVoiceTakeStore', () {
    late _RawStore raw;
    late _InMemoryKeyValueStore purgeMarkers;
    late UserScopedVoiceTakeStore store;

    setUp(() {
      raw = _RawStore();
      purgeMarkers = _InMemoryKeyValueStore();
      store = UserScopedVoiceTakeStore(raw, pendingPurgeStorage: purgeMarkers);
    });

    test('saveTake/takesFor round-trip for the current user', () async {
      store.setCurrentUser(1);
      await store.saveTake('job_interview', _b([1]));
      await store.saveTake('job_interview', _b([2]));

      final takes = await store.takesFor('job_interview');
      expect(takes!.baseline, _b([1]));
      expect(takes.latest, _b([2]));
    });

    test('every key handed to the inner store is prefixed with the current '
        'user id, not the bare skill', () async {
      store.setCurrentUser(42);
      await store.saveTake('job_interview', _b([1]));

      expect(raw.baseline.containsKey('job_interview'), isFalse);
      expect(raw.baseline.containsKey('42:job_interview'), isTrue);
    });

    group('cross-account replay prevention (#319, primary scenario)', () {
      test('a DIFFERENT user never sees takes saved under the same skill '
          'name, even when the underlying store still holds them', () async {
        // User A saves takes for a skill slug B will also use — shared
        // scenario slugs are the norm (e.g. "job_interview"), not the
        // exception. A's data is deliberately left in `raw` (simulating a
        // failed/never-attempted purge) to isolate what key-scoping alone
        // buys, independent of the pending-purge gate.
        store.setCurrentUser(1);
        await store.saveTake('job_interview', _b([10]));
        await store.saveTake('job_interview', _b([11]));

        // User B signs in on the SAME device/store instance.
        store.setCurrentUser(2);

        expect(await store.takesFor('job_interview'), isNull);
      });

      test('B can save and read their OWN take for the same skill slug '
          'while A\'s data is untouched underneath', () async {
        store.setCurrentUser(1);
        await store.saveTake('job_interview', _b([10]));
        await store.saveTake('job_interview', _b([11]));

        store.setCurrentUser(2);
        await store.saveTake('job_interview', _b([20]));
        await store.saveTake('job_interview', _b([21]));

        final bTakes = await store.takesFor('job_interview');
        expect(bTakes!.baseline, _b([20]));
        expect(bTakes.latest, _b([21]));

        // A's own data, read back under A's own session, is unaffected.
        store.setCurrentUser(1);
        final aTakes = await store.takesFor('job_interview');
        expect(aTakes!.baseline, _b([10]));
        expect(aTakes.latest, _b([11]));
      });
    });

    group('blocked reads until a failed logout purge is confirmed (#319)', () {
      test('eraseAll failing blocks takesFor for the SAME user afterwards',
          () async {
        store.setCurrentUser(1);
        await store.saveTake('a', _b([1]));
        await store.saveTake('a', _b([2]));
        raw.throwOnEraseAll = StateError('keystore unavailable');

        await expectLater(store.eraseAll(), throwsStateError);

        // Still user 1 (a real app would sign out right after; simulate the
        // window where the purge just failed and the app hasn't yet cleared
        // the session) — reads must be blocked, not return the "erased" data.
        expect(await store.takesFor('a'), isNull);
      });

      test('the block survives signing out and the SAME user signing back '
          'in — an "erased" take must not quietly reappear', () async {
        store.setCurrentUser(1);
        await store.saveTake('a', _b([1]));
        await store.saveTake('a', _b([2]));
        raw.throwOnEraseAll = StateError('keystore unavailable');
        await expectLater(store.eraseAll(), throwsStateError);

        store.setCurrentUser(null); // signed out
        store.setCurrentUser(1); // signs back in on this device

        expect(await store.takesFor('a'), isNull);
      });

      test('a DIFFERENT user is never blocked by another user\'s failed '
          'purge — their own data was never at risk', () async {
        store.setCurrentUser(1);
        await store.saveTake('a', _b([1]));
        await store.saveTake('a', _b([2]));
        raw.throwOnEraseAll = StateError('keystore unavailable');
        await expectLater(store.eraseAll(), throwsStateError);

        store.setCurrentUser(2);
        await store.saveTake('a', _b([9]));
        await store.saveTake('a', _b([10]));

        final takes = await store.takesFor('a');
        expect(takes!.baseline, _b([9])); // user 2's own data, not blocked
      });

      test('a LATER successful eraseAll for the tainted user clears the '
          'block', () async {
        store.setCurrentUser(1);
        await store.saveTake('a', _b([1]));
        await store.saveTake('a', _b([2]));
        raw.throwOnEraseAll = StateError('keystore unavailable');
        await expectLater(store.eraseAll(), throwsStateError);
        expect(await store.takesFor('a'), isNull); // blocked

        raw.throwOnEraseAll = null; // the retry succeeds this time
        await store.eraseAll();

        // Nothing was left to read (eraseAll really did wipe it) but the
        // block itself is gone — a NEW take is readable again.
        await store.saveTake('a', _b([5]));
        await store.saveTake('a', _b([6]));
        final takes = await store.takesFor('a');
        expect(takes!.baseline, _b([5]));
      });

      test('a successful eraseAll by ANY user clears a pending purge left '
          'by a DIFFERENT user — eraseAll wipes everything, so the taint is '
          'moot either way', () async {
        store.setCurrentUser(1);
        await store.saveTake('a', _b([1]));
        await store.saveTake('a', _b([2]));
        raw.throwOnEraseAll = StateError('keystore unavailable');
        await expectLater(store.eraseAll(), throwsStateError);

        store.setCurrentUser(2);
        raw.throwOnEraseAll = null; // user 2's own erase succeeds
        await store.eraseAll(); // an unrelated, successful erase

        store.setCurrentUser(1);
        await store.saveTake('a', _b([7]));
        await store.saveTake('a', _b([8]));
        final takes = await store.takesFor('a');
        expect(takes!.baseline, _b([7])); // no longer blocked
      });

      test('a SECOND, unrelated user\'s failed purge does not silently '
          'un-block an EARLIER tainted user — both stay blocked', () async {
        // A single-slot design (last failure wins) would lose track of A the
        // moment B's own purge also fails, letting A's "erased" takes
        // silently reappear even though A's purge was never confirmed.
        store.setCurrentUser(1);
        await store.saveTake('a', _b([1]));
        await store.saveTake('a', _b([2]));
        raw.throwOnEraseAll = StateError('keystore unavailable');
        await expectLater(store.eraseAll(), throwsStateError);

        store.setCurrentUser(2);
        await store.saveTake('a', _b([9]));
        await store.saveTake('a', _b([10]));
        await expectLater(store.eraseAll(), throwsStateError); // also fails

        store.setCurrentUser(1);
        expect(await store.takesFor('a'), isNull); // A still blocked

        store.setCurrentUser(2);
        expect(await store.takesFor('a'), isNull); // B still blocked too
      });

      test('a concurrent eraseAll failure is not clobbered by an in-flight, '
          'now-stale pending-purge read', () async {
        // Deterministic reproduction of the race: a takesFor() read starts
        // (and suspends mid-way, reading "nothing pending" from storage)
        // WHILE a concurrent eraseAll() fails and durably records the taint.
        // Without the re-check-after-await guard, the read's stale result
        // would win when it finally resolves, silently discarding the
        // concurrent write and un-blocking the tainted user for the rest of
        // the app session.
        final delayable = _DelayableReadKeyValueStore();
        final s = UserScopedVoiceTakeStore(raw, pendingPurgeStorage: delayable);
        s.setCurrentUser(1);
        await s.saveTake('a', _b([1]));
        await s.saveTake('a', _b([2]));

        delayable.blockNextRead();
        final readFuture = s.takesFor('a'); // suspends inside _pendingPurges()

        raw.throwOnEraseAll = StateError('keystore unavailable');
        await expectLater(s.eraseAll(), throwsStateError); // fully resolves

        delayable.releaseRead(); // let the stale read finally complete
        final result = await readFuture;

        expect(result, isNull); // reflects the FRESH taint, not the stale read
      });

      test('the pending-purge marker survives a fresh instance over the '
          'same marker storage (an app restart between accounts)', () async {
        store.setCurrentUser(1);
        await store.saveTake('a', _b([1]));
        await store.saveTake('a', _b([2]));
        raw.throwOnEraseAll = StateError('keystore unavailable');
        await expectLater(store.eraseAll(), throwsStateError);

        // A brand-new wrapper instance, same underlying inner store AND
        // marker storage — simulates the app process restarting.
        final restarted = UserScopedVoiceTakeStore(
          raw,
          pendingPurgeStorage: purgeMarkers,
        );
        restarted.setCurrentUser(1);

        expect(await restarted.takesFor('a'), isNull); // still blocked
      });
    });

    group('no signed-in user', () {
      test('saveTake refuses rather than silently writing under a stale '
          'or absent identity', () async {
        expect(
          () => store.saveTake('a', _b([1])),
          throwsA(isA<StateError>()),
        );
      });

      test('takesFor refuses rather than silently reading nothing (a bug — '
          'voice features should never be reachable while signed out — must '
          'surface, not be masked as "no comparison yet")', () async {
        expect(() => store.takesFor('a'), throwsA(isA<StateError>()));
      });

      test('deleteSkill refuses for the same reason', () async {
        expect(() => store.deleteSkill('a'), throwsA(isA<StateError>()));
      });

      test('eraseAll does not require a current user (logout can purge '
          'even if the session was already cleared)', () async {
        await store.eraseAll(); // must not throw
        expect(raw.eraseAllCalls, 1);
      });
    });

    test('deleteSkill scopes to the current user like saveTake/takesFor',
        () async {
      store.setCurrentUser(1);
      await store.saveTake('a', _b([1]));

      await store.deleteSkill('a');

      expect(raw.baseline.containsKey('1:a'), isFalse);
    });
  });
}

import 'dart:io';
import 'dart:typed_data';

import 'package:apm/src/core/audio/encrypted_voice_take_store.dart';
import 'package:apm/src/core/audio/file_voice_take_store.dart';
import 'package:apm/src/core/audio/ttl_voice_take_store.dart';
import 'package:apm/src/core/audio/user_scoped_voice_take_store.dart';
import 'package:apm/src/core/storage/key_value_store.dart';
import 'package:flutter_test/flutter_test.dart';

/// Exercises the REAL composed chain exactly as
/// persistent_voice_take_store_io.dart wires it —
/// `UserScopedVoiceTakeStore(TtlVoiceTakeStore(EncryptedVoiceTakeStore(
/// FileVoiceTakeStore(...))))` — rather than each wrapper in isolation
/// against a simplified fake. The other test files unit-test each layer's
/// OWN logic; this one exists specifically because a layer can be locally
/// correct yet break when composed (a real bug caught in review: #319's
/// user-scoping always introduces a ':' into every key, #321's sweep feeds
/// [SkillEnumerator.knownSkills]'s post-[FileVoiceTakeStore]-`_safe()` stem
/// back into a read, and #320's AAD was originally derived from whatever
/// string [EncryptedVoiceTakeStore] happened to receive — three individually
///-reasonable fixes that, composed, computed a DIFFERENT AAD on a
/// sweep-triggered read than the one used at save time, silently purging
/// every take as "corrupt" on every app restart).
class _InMemoryKeyValueStore implements KeyValueStore {
  final Map<String, String> _m = {};
  @override
  Future<String?> read(String key) async => _m[key];
  @override
  Future<void> write(String key, String value) async => _m[key] = value;
  @override
  Future<void> delete(String key) async => _m.remove(key);
}

Uint8List _b(List<int> bytes) => Uint8List.fromList(bytes);

void main() {
  group('the real composed chain (Ttl(Encrypted(File)) wrapped by '
      'UserScoped)', () {
    late Directory dir;
    late _InMemoryKeyValueStore sharedStorage;

    setUp(() async {
      dir = await Directory.systemTemp.createTemp('voice_takes_chain_test');
      sharedStorage = _InMemoryKeyValueStore();
    });
    tearDown(() async {
      if (await dir.exists()) await dir.delete(recursive: true);
    });

    UserScopedVoiceTakeStore buildStore() {
      final ttl = TtlVoiceTakeStore(
        EncryptedVoiceTakeStore(
          FileVoiceTakeStore(() async => dir),
          keyStorage: sharedStorage,
        ),
      );
      return UserScopedVoiceTakeStore(ttl, pendingPurgeStorage: sharedStorage);
    }

    test('a take saved, then swept (simulating the startup sweep after an '
        'app restart), is still readable — NOT wrongly purged as '
        'undecryptable (#319+#320+#321 composition)', () async {
      final store = buildStore();
      store.setCurrentUser(7);
      await store.saveTake('job_interview', _b([1, 2, 3]));
      await store.saveTake('job_interview', _b([4, 5, 6]));

      // A fresh chain over the SAME directory + key storage — an app
      // restart — exactly as persistent_voice_take_store_io.dart builds it.
      final ttlAfterRestart = TtlVoiceTakeStore(
        EncryptedVoiceTakeStore(
          FileVoiceTakeStore(() async => dir),
          keyStorage: sharedStorage,
        ),
      );
      await ttlAfterRestart.sweepExpired(); // the #321 startup sweep

      final restarted = UserScopedVoiceTakeStore(
        ttlAfterRestart,
        pendingPurgeStorage: sharedStorage,
      );
      restarted.setCurrentUser(7);
      final takes = await restarted.takesFor('job_interview');

      expect(takes, isNotNull);
      expect(takes!.baseline, _b([1, 2, 3]));
      expect(takes.latest, _b([4, 5, 6]));
    });

    test('the sweep still purges a GENUINELY expired take in the real '
        'composed chain', () async {
      final now = DateTime.utc(2026, 1, 1);
      var clock = now;
      final ttl = TtlVoiceTakeStore(
        EncryptedVoiceTakeStore(
          FileVoiceTakeStore(() async => dir),
          keyStorage: sharedStorage,
        ),
        ttl: const Duration(days: 30),
        now: () => clock,
      );
      final store = UserScopedVoiceTakeStore(ttl, pendingPurgeStorage: sharedStorage);
      store.setCurrentUser(7);
      await store.saveTake('job_interview', _b([1]));
      clock = clock.add(const Duration(days: 30) + const Duration(seconds: 1));
      await store.saveTake('job_interview', _b([2]));

      await ttl.sweepExpired();

      expect(await store.takesFor('job_interview'), isNull);
    });

    test('two different users\' takes for the same skill slug both survive '
        'independently across a save -> sweep -> read cycle', () async {
      final store = buildStore();
      store.setCurrentUser(1);
      await store.saveTake('job_interview', _b([10]));
      await store.saveTake('job_interview', _b([11]));
      store.setCurrentUser(2);
      await store.saveTake('job_interview', _b([20]));
      await store.saveTake('job_interview', _b([21]));

      final ttlAfterRestart = TtlVoiceTakeStore(
        EncryptedVoiceTakeStore(
          FileVoiceTakeStore(() async => dir),
          keyStorage: sharedStorage,
        ),
      );
      await ttlAfterRestart.sweepExpired();
      final restarted = UserScopedVoiceTakeStore(
        ttlAfterRestart,
        pendingPurgeStorage: sharedStorage,
      );

      restarted.setCurrentUser(1);
      final aTakes = await restarted.takesFor('job_interview');
      expect(aTakes!.baseline, _b([10]));

      restarted.setCurrentUser(2);
      final bTakes = await restarted.takesFor('job_interview');
      expect(bTakes!.baseline, _b([20]));
    });
  });
}

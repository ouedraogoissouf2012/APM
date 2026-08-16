import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:apm/src/core/audio/encrypted_voice_take_store.dart';
import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:apm/src/core/storage/key_value_store.dart';
import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';

/// A raw in-memory [VoiceTakeStore] with no encryption of its own — stands in
/// for whichever real store (file/IndexedDB) [EncryptedVoiceTakeStore] wraps,
/// exposing what was ACTUALLY handed to it so a test can assert the bytes on
/// "disk" are ciphertext, not the learner's plaintext audio.
class _RawStore implements VoiceTakeStore {
  final Map<String, Uint8List> _baseline = {};
  final Map<String, Uint8List> _latest = {};
  final List<String> deleteSkillCalls = [];
  int eraseAllCalls = 0;
  Completer<void>? saveGate;

  @override
  Future<void> saveTake(String skill, Uint8List bytes) async {
    if (saveGate != null) await saveGate!.future;
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

  /// Test-only seam: what the wrapper actually delegated for [skill]'s
  /// baseline — used to confirm it's ciphertext, not plaintext.
  Uint8List? peekBaseline(String skill) => _baseline[skill];

  /// Test-only seam: simulates bytes that somehow survived a physical
  /// delete (e.g. an inner-store bug) — written directly, bypassing the
  /// wrapper's encryption.
  void seedRaw(String skill, Uint8List baseline, Uint8List latest) {
    _baseline[skill] = baseline;
    _latest[skill] = latest;
  }
}

/// A [_RawStore] variant that ALSO supports enumeration — stands in for a
/// real inner store (file/IndexedDB), which does, to test
/// [EncryptedVoiceTakeStore.knownSkills]'s pass-through.
class _EnumerableRawStore extends _RawStore implements SkillEnumerator {
  @override
  Future<Set<String>> knownSkills() async => {..._baseline.keys, ..._latest.keys};
}

class _InMemoryKeyValueStore implements KeyValueStore {
  final Map<String, String> _m = {};
  int deleteCalls = 0;

  @override
  Future<String?> read(String key) async => _m[key];
  @override
  Future<void> write(String key, String value) async => _m[key] = value;
  @override
  Future<void> delete(String key) async {
    deleteCalls++;
    _m.remove(key);
  }
}

Uint8List _b(List<int> bytes) => Uint8List.fromList(bytes);

void main() {
  group('EncryptedVoiceTakeStore', () {
    late _RawStore raw;
    late _InMemoryKeyValueStore keyStorage;
    late EncryptedVoiceTakeStore store;

    setUp(() {
      raw = _RawStore();
      keyStorage = _InMemoryKeyValueStore();
      store = EncryptedVoiceTakeStore(raw, keyStorage: keyStorage);
    });

    test('a saved take round-trips to the exact original bytes', () async {
      await store.saveTake('job_interview', _b([1, 2, 3]));
      await store.saveTake('job_interview', _b([4, 5, 6]));

      final takes = await store.takesFor('job_interview');

      expect(takes, isNotNull);
      expect(takes!.baseline, _b([1, 2, 3]));
      expect(takes.latest, _b([4, 5, 6]));
    });

    test('the bytes handed to the inner store are ciphertext, not the '
        "learner's plaintext audio (#226)", () async {
      final plaintext = _b(List.generate(32, (i) => i));
      await store.saveTake('a', plaintext);

      final stored = raw.peekBaseline('a');

      expect(stored, isNotNull);
      expect(stored, isNot(plaintext));
      // Longer than the plaintext: AES-GCM appends a nonce + a 16-byte MAC.
      expect(stored!.length, greaterThan(plaintext.length));
    });

    test('a fresh EncryptedVoiceTakeStore over the same key storage decrypts '
        'takes saved by a previous instance (survives a restart)', () async {
      await store.saveTake('a', _b([1]));
      await store.saveTake('a', _b([2, 2]));

      final restarted = EncryptedVoiceTakeStore(raw, keyStorage: keyStorage);
      final takes = await restarted.takesFor('a');

      expect(takes!.baseline, _b([1]));
      expect(takes.latest, _b([2, 2]));
    });

    test('a legacy PLAINTEXT take (saved before encryption existed) is '
        'treated as absent, not a crash', () async {
      // A real WAV starts with "RIFF...." — exactly what a learner's take
      // saved by a pre-#226 app version still has on disk.
      final legacyWav = _b([0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00]);
      raw.seedRaw('a', legacyWav, legacyWav);

      final takes = await store.takesFor('a');

      expect(takes, isNull);
    });

    test('an undecryptable take is physically purged so the next save can '
        'start a genuinely fresh baseline (#226)', () async {
      raw.seedRaw('a', _b([1, 2, 3, 4, 5, 6, 7, 8]), _b([1, 2, 3, 4, 5, 6, 7, 8]));

      await store.takesFor('a'); // the read that notices it can't decrypt

      expect(raw.deleteSkillCalls, ['a']);
    });

    test('eraseAll deletes the encryption key AND forwards to the inner '
        'store', () async {
      await store.saveTake('a', _b([1]));

      await store.eraseAll();

      expect(keyStorage.deleteCalls, 1);
      expect(raw.eraseAllCalls, 1);
    });

    test('crypto-shredding: bytes that somehow survive a physical delete '
        'become permanently unreadable once eraseAll destroys the key',
        () async {
      await store.saveTake('a', _b([1]));
      await store.saveTake('a', _b([2]));
      final survivingCiphertext = raw.peekBaseline('a')!;

      await store.eraseAll(); // destroys the key; raw.eraseAll() clears raw too
      // Simulate the surviving-bytes edge case eraseAll is a backstop for.
      raw.seedRaw('a', survivingCiphertext, survivingCiphertext);

      // A fresh instance sharing the SAME (now-empty) key storage gets a
      // brand-new key — the old ciphertext no longer decrypts under it.
      final afterErase = EncryptedVoiceTakeStore(raw, keyStorage: keyStorage);
      expect(await afterErase.takesFor('a'), isNull);
    });

    test('#430: a saveTake started before eraseAll does not recreate files',
        () async {
      await store.saveTake('a', _b([1]));
      raw.saveGate = Completer<void>();
      final pending = store.saveTake('a', _b([2]));
      await Future<void>.delayed(Duration.zero);
      await store.eraseAll();
      raw.saveGate!.complete();
      await pending;

      expect(raw.peekBaseline('a'), isNull);
      expect(await store.takesFor('a'), isNull);
    });

    test('deleteSkill forwards to the inner store', () async {
      await store.deleteSkill('a');
      expect(raw.deleteSkillCalls, ['a']);
    });

    test('distinct skills are independently encrypted and decrypted',
        () async {
      await store.saveTake('restaurant', _b([1]));
      await store.saveTake('restaurant', _b([2]));
      await store.saveTake('travel', _b([3]));
      await store.saveTake('travel', _b([4]));

      expect((await store.takesFor('restaurant'))!.latest, _b([2]));
      expect((await store.takesFor('travel'))!.latest, _b([4]));
    });

    group('AAD binding (#320)', () {
      test('a ciphertext copied from a DIFFERENT skill fails to decrypt '
          'instead of being silently replayed', () async {
        // The exact attack #320 describes: a raw storage-level write copies
        // one skill's ciphertext into another's slot; the GCM tag alone
        // would still verify (same key), so only the AAD binding catches it.
        await store.saveTake('restaurant', _b([1]));
        await store.saveTake('restaurant', _b([2]));
        final stolenBaseline = raw.peekBaseline('restaurant')!;

        raw.seedRaw('job_interview', stolenBaseline, stolenBaseline);

        // Not restaurant's [1] replayed as job_interview's proof — absent.
        expect(await store.takesFor('job_interview'), isNull);
        expect(raw.deleteSkillCalls, contains('job_interview'));
      });

      test('a ciphertext saved WITHOUT the aad binding (pre-#320) is cleanly '
          'invalidated, not a crash', () async {
        // Simulates a take encrypted by the app version before this fix —
        // same key, same algorithm, but no associated data at all.
        final legacyKey = await keyStorage.read('voice_take_encryption_key_v1');
        expect(legacyKey, isNull); // nothing generated yet
        final algorithm = AesGcm.with256bits();
        final key = await algorithm.newSecretKey();
        await keyStorage.write(
          'voice_take_encryption_key_v1',
          base64Encode(await key.extractBytes()),
        );
        final box = await algorithm.encrypt(_b([7, 7, 7]), secretKey: key);
        raw.seedRaw('a', box.concatenation(), box.concatenation());

        expect(await store.takesFor('a'), isNull);
        expect(raw.deleteSkillCalls, ['a']);
      });
    });

    group('knownSkills (#321)', () {
      test('forwards to the inner store when it supports enumeration',
          () async {
        final enumerableRaw = _EnumerableRawStore();
        final s = EncryptedVoiceTakeStore(enumerableRaw, keyStorage: keyStorage);
        await s.saveTake('restaurant', _b([1]));

        expect(await s.knownSkills(), {'restaurant'});
      });

      test('returns empty, not a crash, when the inner store cannot '
          'enumerate', () async {
        // `raw` (_RawStore) deliberately does not implement SkillEnumerator.
        expect(await store.knownSkills(), isEmpty);
      });
    });
  });
}

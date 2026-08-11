@TestOn('browser')
library;

import 'dart:typed_data';

import 'package:apm/src/core/audio/encrypted_voice_take_store.dart';
import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:apm/src/core/storage/key_value_store.dart';
import 'package:flutter_test/flutter_test.dart';

/// Runtime proof that AES-256-GCM encryption/decryption actually works on the
/// WEB build (#226), which can't run on the Dart VM. `package:cryptography`
/// selects the Web Crypto API (`crypto.subtle`) here rather than its
/// pure-Dart implementation — this is the path that would break if that
/// selection (or any 64-bit `ByteData` operation hiding in either path, the
/// exact class of bug #226's TTL header fix already hit once) were wrong. The
/// VM suite (`encrypted_voice_take_store_test.dart`) covers the store's
/// LOGIC with the same real [EncryptedVoiceTakeStore] and default algorithm;
/// this only needs to prove the browser path encrypts and decrypts correctly.
class _RawStore implements VoiceTakeStore {
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
    if (baseline == null || latest == null) return null;
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

void main() {
  test('AES-256-GCM round-trips real audio-sized bytes in a real browser',
      () async {
    final raw = _RawStore();
    final keyStorage = _InMemoryKeyValueStore();
    final store = EncryptedVoiceTakeStore(raw, keyStorage: keyStorage);
    // A few KB, standing in for a short WAV clip — big enough to exercise more
    // than a single AES block.
    final plaintext = Uint8List.fromList(
      List.generate(4096, (i) => i % 256),
    );

    await store.saveTake('job_interview', Uint8List.fromList([1]));
    await store.saveTake('job_interview', plaintext);

    final takes = await store.takesFor('job_interview');
    expect(takes, isNotNull);
    expect(takes!.latest, plaintext);
    // What actually sits in the inner store is NOT the plaintext.
    expect(raw._latest['job_interview'], isNot(plaintext));
  });

  test('a fresh store instance over the same key storage decrypts a take '
      'saved by a previous instance (survives a reload)', () async {
    final raw = _RawStore();
    final keyStorage = _InMemoryKeyValueStore();
    final store = EncryptedVoiceTakeStore(raw, keyStorage: keyStorage);
    await store.saveTake('a', Uint8List.fromList([1, 1, 1]));
    await store.saveTake('a', Uint8List.fromList([2, 2, 2]));

    final reopened = EncryptedVoiceTakeStore(raw, keyStorage: keyStorage);
    final takes = await reopened.takesFor('a');

    expect(takes, isNotNull);
    expect(takes!.baseline, Uint8List.fromList([1, 1, 1]));
    expect(takes.latest, Uint8List.fromList([2, 2, 2]));
  });
}

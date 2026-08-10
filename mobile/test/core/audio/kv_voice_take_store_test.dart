import 'dart:typed_data';

import 'package:apm/src/core/audio/kv_voice_take_store.dart';
import 'package:flutter_test/flutter_test.dart';

/// In-memory fake of the persistence seam. Standing in for IndexedDB, it lets us
/// unit-test the baseline/latest/distinct LOGIC on the VM — and, by surviving
/// across [KvVoiceTakeStore] instances, it models IndexedDB persisting a reload.
class _FakeKv implements VoiceTakeKvStore {
  final Map<String, Uint8List> _m = {};
  @override
  Future<Uint8List?> read(String key) async => _m[key];
  @override
  Future<void> write(String key, Uint8List bytes) async => _m[key] = bytes;
  @override
  Future<void> clear() async => _m.clear();
}

Uint8List _b(List<int> bytes) => Uint8List.fromList(bytes);

void main() {
  test('no before/after until there are two distinct takes', () async {
    final store = KvVoiceTakeStore(_FakeKv());
    expect(await store.takesFor('restaurant'), isNull);
    await store.saveTake('restaurant', _b([1, 2, 3]));
    // A single take is not a before/after yet.
    expect(await store.takesFor('restaurant'), isNull);
  });

  test('exposes the first take as baseline and the most recent as latest',
      () async {
    final store = KvVoiceTakeStore(_FakeKv());
    await store.saveTake('restaurant', _b([1, 1, 1]));
    await store.saveTake('restaurant', _b([2, 2, 2]));
    final takes = await store.takesFor('restaurant');
    expect(takes, isNotNull);
    expect(takes!.baseline, _b([1, 1, 1]));
    expect(takes.latest, _b([2, 2, 2]));
  });

  test('baseline stays the very first take across further saves', () async {
    final store = KvVoiceTakeStore(_FakeKv());
    await store.saveTake('s', _b([1]));
    await store.saveTake('s', _b([2]));
    await store.saveTake('s', _b([3]));
    final takes = await store.takesFor('s');
    expect(takes!.baseline, _b([1]));
    expect(takes.latest, _b([3]));
  });

  test('persists across store instances sharing the KV (survives a reload)',
      () async {
    final kv = _FakeKv();
    await KvVoiceTakeStore(kv).saveTake('travel', _b([9]));
    await KvVoiceTakeStore(kv).saveTake('travel', _b([8]));
    // A brand-new store over the same persistent KV still sees the before/after —
    // exactly what IndexedDB buys us over the old in-memory web fallback.
    final takes = await KvVoiceTakeStore(kv).takesFor('travel');
    expect(takes!.baseline, _b([9]));
    expect(takes.latest, _b([8]));
  });

  test('two takes with identical bytes are not a before/after', () async {
    final store = KvVoiceTakeStore(_FakeKv());
    await store.saveTake('s', _b([5, 5]));
    await store.saveTake('s', _b([5, 5]));
    expect(await store.takesFor('s'), isNull);
  });

  test('distinct skills keep separate baselines and latests', () async {
    final kv = _FakeKv();
    final store = KvVoiceTakeStore(kv);
    await store.saveTake('restaurant', _b([1]));
    await store.saveTake('restaurant', _b([2]));
    await store.saveTake('job_interview', _b([3]));
    await store.saveTake('job_interview', _b([4]));
    expect((await store.takesFor('restaurant'))!.latest, _b([2]));
    expect((await store.takesFor('job_interview'))!.latest, _b([4]));
  });

  test('eraseAll wipes every take for every skill (#219)', () async {
    final kv = _FakeKv();
    final store = KvVoiceTakeStore(kv);
    await store.saveTake('restaurant', _b([1]));
    await store.saveTake('restaurant', _b([2]));
    await store.saveTake('travel', _b([3]));
    await store.saveTake('travel', _b([4]));

    await store.eraseAll();

    expect(await store.takesFor('restaurant'), isNull);
    expect(await store.takesFor('travel'), isNull);
    // A fresh store over the same (now-empty) KV sees nothing — the bytes are
    // gone, not just hidden. And the store still works afterwards.
    final fresh = KvVoiceTakeStore(kv);
    expect(await fresh.takesFor('restaurant'), isNull);
    await fresh.saveTake('restaurant', _b([9]));
    await fresh.saveTake('restaurant', _b([8]));
    expect((await fresh.takesFor('restaurant'))!.baseline, _b([9]));
  });
}

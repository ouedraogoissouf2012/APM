@TestOn('browser')
library;

import 'dart:typed_data';

import 'package:apm/src/core/audio/indexed_db_voice_take_kv.dart';
import 'package:apm/src/core/audio/kv_voice_take_store.dart';
import 'package:flutter_test/flutter_test.dart';

/// Runtime proof of the IndexedDB adapter (#205), which can't run on the Dart VM.
/// The VM suite covers the take LOGIC via a fake KV; this covers the real
/// browser store: bytes written by one connection are readable by a fresh one —
/// i.e. they survive a reload, which the old in-memory fallback did not.
void main() {
  test('IndexedDB persists takes across a fresh connection (real browser)',
      () async {
    // Unique per run so re-runs don't collide in the shared browser database.
    final skill = 'e2e_${DateTime.now().microsecondsSinceEpoch}';

    final store = KvVoiceTakeStore(IndexedDbVoiceTakeKv());
    expect(await store.takesFor(skill), isNull);
    await store.saveTake(skill, Uint8List.fromList([1, 1, 1]));
    // One take is not a before/after yet.
    expect(await store.takesFor(skill), isNull);
    await store.saveTake(skill, Uint8List.fromList([2, 2, 2]));

    // A brand-new adapter = a fresh IndexedDB connection. The before/after must
    // still be there — the whole point of persisting on web.
    final reopened = KvVoiceTakeStore(IndexedDbVoiceTakeKv());
    final takes = await reopened.takesFor(skill);
    expect(takes, isNotNull);
    expect(takes!.baseline, Uint8List.fromList([1, 1, 1]));
    expect(takes.latest, Uint8List.fromList([2, 2, 2]));
  });

  test('keys() enumerates entries in the real IndexedDB store (#321)',
      () async {
    // Unique per run so re-runs don't collide in the shared browser database.
    final key = 'e2e_keys_${DateTime.now().microsecondsSinceEpoch}';
    final kv = IndexedDbVoiceTakeKv();

    await kv.write(key, Uint8List.fromList([1]));

    expect(await kv.keys(), contains(key));

    await kv.delete(key);

    expect(await kv.keys(), isNot(contains(key)));
  });
}

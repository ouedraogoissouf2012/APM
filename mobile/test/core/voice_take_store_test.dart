import 'dart:typed_data';

import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:flutter_test/flutter_test.dart';

Uint8List _bytes(List<int> b) => Uint8List.fromList(b);

void main() {
  test('needs two DISTINCT takes before exposing a before/after (#199)', () async {
    final store = InMemoryVoiceTakeStore();
    expect(await store.takesFor('s'), isNull); // nothing yet

    await store.saveTake('s', _bytes([1]));
    expect(await store.takesFor('s'), isNull); // only a baseline — no "after" yet

    await store.saveTake('s', _bytes([2, 3]));
    final takes = await store.takesFor('s');
    expect(takes, isNotNull);
    expect(takes!.baseline, [1]); // baseline stays the first take
    expect(takes.latest, [2, 3]); // latest is the most recent
  });

  test('a third take updates latest but keeps the original baseline', () async {
    final store = InMemoryVoiceTakeStore();
    await store.saveTake('s', _bytes([1]));
    await store.saveTake('s', _bytes([2]));
    await store.saveTake('s', _bytes([3]));
    final takes = await store.takesFor('s');
    expect(takes!.baseline, [1]);
    expect(takes.latest, [3]);
  });

  test('skills are independent', () async {
    final store = InMemoryVoiceTakeStore();
    await store.saveTake('a', _bytes([1]));
    await store.saveTake('b', _bytes([2]));
    expect(await store.takesFor('a'), isNull); // one take each -> nothing to compare
    expect(await store.takesFor('b'), isNull);
  });

  test('knownSkills reports every skill with something stored (#321)',
      () async {
    final store = InMemoryVoiceTakeStore();
    await store.saveTake('a', _bytes([1]));
    await store.saveTake('b', _bytes([2]));

    expect(await store.knownSkills(), {'a', 'b'});
  });

  test('knownSkills is empty after eraseAll', () async {
    final store = InMemoryVoiceTakeStore();
    await store.saveTake('a', _bytes([1]));

    await store.eraseAll();

    expect(await store.knownSkills(), isEmpty);
  });
}

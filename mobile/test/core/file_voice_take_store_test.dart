import 'dart:io';
import 'dart:typed_data';

import 'package:apm/src/core/audio/file_voice_take_store.dart';
import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:flutter_test/flutter_test.dart';

Uint8List _b(List<int> x) => Uint8List.fromList(x);

void main() {
  late Directory dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('voice_takes_test');
  });
  tearDown(() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  });

  VoiceTakeStore store() => FileVoiceTakeStore(() async => dir);

  test('needs two distinct takes; baseline stays first, latest updates', () async {
    final s = store();
    expect(await s.takesFor('skill'), isNull); // nothing yet
    await s.saveTake('skill', _b([1, 2]));
    expect(await s.takesFor('skill'), isNull); // only a baseline
    await s.saveTake('skill', _b([3, 4, 5]));
    final takes = await s.takesFor('skill');
    expect(takes!.baseline, [1, 2]); // first take
    expect(takes.latest, [3, 4, 5]); // most recent
  });

  test('persists across a new store instance (survives a restart)', () async {
    final s1 = store();
    await s1.saveTake('skill', _b([1]));
    await s1.saveTake('skill', _b([2, 2]));

    // A fresh store over the SAME directory — simulates an app restart.
    final s2 = FileVoiceTakeStore(() async => dir);
    final takes = await s2.takesFor('skill');
    expect(takes!.baseline, [1]);
    expect(takes.latest, [2, 2]);
  });

  test('skills are isolated (including unsafe characters in the id)', () async {
    final s = store();
    await s.saveTake('job/interview', _b([1]));
    await s.saveTake('job/interview', _b([2]));
    await s.saveTake('restaurant', _b([9]));

    expect((await s.takesFor('job/interview'))!.latest, [2]);
    expect(await s.takesFor('restaurant'), isNull); // only one take
  });

  test('deleteSkill physically removes the baseline and latest files (#226)',
      () async {
    final s = store();
    await s.saveTake('skill', _b([1]));
    await s.saveTake('skill', _b([2, 2]));
    expect(await File('${dir.path}/skill.baseline').exists(), isTrue);
    expect(await File('${dir.path}/skill.latest').exists(), isTrue);

    await s.deleteSkill('skill');

    expect(await File('${dir.path}/skill.baseline').exists(), isFalse);
    expect(await File('${dir.path}/skill.latest').exists(), isFalse);
    expect(await s.takesFor('skill'), isNull);
  });

  test('deleteSkill on an absent skill (or before the directory even '
      'exists) is a no-op, not an error', () async {
    final s = store();
    await s.deleteSkill('never-saved'); // must not throw
    await s.saveTake('never-saved', _b([1]));
    await s.saveTake('never-saved', _b([2]));
    expect((await s.takesFor('never-saved'))!.latest, [2]); // still usable after
  });

  test('a physically purged skill can start a genuinely fresh baseline',
      () async {
    // Regression guard: FileVoiceTakeStore.saveTake only writes a NEW
    // baseline "if !exists()" — without a real delete, a stale baseline file
    // would keep being treated as the baseline forever.
    final s = store();
    await s.saveTake('skill', _b([1]));
    await s.saveTake('skill', _b([2]));
    await s.deleteSkill('skill');

    await s.saveTake('skill', _b([9]));
    await s.saveTake('skill', _b([10]));

    expect((await s.takesFor('skill'))!.baseline, [9]); // NOT the old [1]
  });

  test('knownSkills reports every skill with something stored (#321)',
      () async {
    final s = FileVoiceTakeStore(() async => dir);
    await s.saveTake('restaurant', _b([1]));
    await s.saveTake('restaurant', _b([2]));
    await s.saveTake('job_interview', _b([3]));

    expect(await s.knownSkills(), {'restaurant', 'job_interview'});
  });

  test('knownSkills is empty when the directory has never been created',
      () async {
    final emptyDir = Directory('${dir.path}/never-created');
    final s = FileVoiceTakeStore(() async => emptyDir);

    expect(await s.knownSkills(), isEmpty);
  });
}

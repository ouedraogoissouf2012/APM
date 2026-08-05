import 'package:apm/src/data/models/mission.dart';
import 'package:apm/src/data/repositories/mission_repository.dart';
import 'package:apm/src/ui/missions/view_model/mission_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockMissionRepo extends Mock implements MissionRepository {}

Mission _brief() => const Mission(
  id: 7,
  sourceType: 'offer',
  persona: 'A recruiter',
  goal: 'Pass the screening',
  likelyQuestions: ['Tell me about yourself'],
);

ProviderContainer _container(MissionRepository repo) {
  final c = ProviderContainer(
    overrides: [missionRepositoryProvider.overrideWithValue(repo)],
  );
  addTearDown(c.dispose);
  return c;
}

void main() {
  setUpAll(() => registerFallbackValue(MissionSourceType.offer));

  test('compile success stores the brief and marks ready', () async {
    final repo = _MockMissionRepo();
    when(
      () => repo.compile(
        sourceType: any(named: 'sourceType'),
        content: any(named: 'content'),
      ),
    ).thenAnswer((_) async => _brief());
    final c = _container(repo);

    final ok = await c
        .read(missionViewModelProvider.notifier)
        .compile('a real job offer');

    expect(ok, isTrue);
    final state = c.read(missionViewModelProvider);
    expect(state.status, MissionStatus.ready);
    expect(state.mission?.persona, 'A recruiter');
  });

  test('a blank input is rejected without a network call', () async {
    final repo = _MockMissionRepo();
    final c = _container(repo);

    final ok = await c
        .read(missionViewModelProvider.notifier)
        .compile('   ');

    expect(ok, isFalse);
    verifyNever(
      () => repo.compile(
        sourceType: any(named: 'sourceType'),
        content: any(named: 'content'),
      ),
    );
  });

  test('a failed compile reports failure without throwing', () async {
    final repo = _MockMissionRepo();
    when(
      () => repo.compile(
        sourceType: any(named: 'sourceType'),
        content: any(named: 'content'),
      ),
    ).thenThrow(Exception('down'));
    final c = _container(repo);

    final ok = await c
        .read(missionViewModelProvider.notifier)
        .compile('offer text');

    expect(ok, isFalse);
    expect(c.read(missionViewModelProvider).status, MissionStatus.failed);
  });

  test('changing the source type clears a previously compiled brief', () async {
    final repo = _MockMissionRepo();
    when(
      () => repo.compile(
        sourceType: any(named: 'sourceType'),
        content: any(named: 'content'),
      ),
    ).thenAnswer((_) async => _brief());
    final c = _container(repo);
    final vm = c.read(missionViewModelProvider.notifier);

    await vm.compile('offer');
    expect(c.read(missionViewModelProvider).mission, isNotNull);

    vm.selectSourceType(MissionSourceType.cv);
    final state = c.read(missionViewModelProvider);
    expect(state.sourceType, MissionSourceType.cv);
    expect(state.mission, isNull); // stale brief cleared
    expect(state.status, MissionStatus.idle);
  });
}

import 'package:apm/src/data/models/mission.dart';
import 'package:apm/src/data/repositories/mission_repository.dart';
import 'package:apm/src/ui/missions/view_model/mission_view_model.dart';
import 'package:apm/src/ui/missions/widgets/new_mission_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockMissionRepo extends Mock implements MissionRepository {}

Mission _brief() => const Mission(
  id: 7,
  sourceType: 'offer',
  persona: 'A recruiter for a backend role',
  goal: 'Pass a first-round screening',
  likelyQuestions: ['Tell me about yourself', 'Why this company?'],
);

Future<void> _pump(WidgetTester tester, MissionRepository repo) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [missionRepositoryProvider.overrideWithValue(repo)],
      child: const MaterialApp(home: NewMissionScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() => registerFallbackValue(MissionSourceType.offer));

  testWidgets('compiles and shows the brief before launching', (tester) async {
    final repo = _MockMissionRepo();
    when(
      () => repo.compile(
        sourceType: any(named: 'sourceType'),
        content: any(named: 'content'),
      ),
    ).thenAnswer((_) async => _brief());

    await _pump(tester, repo);

    // Brief is not shown until compiled.
    expect(find.byKey(const Key('mission_brief')), findsNothing);

    await tester.enterText(
      find.byKey(const Key('mission_content')),
      'Senior backend engineer, Python',
    );
    await tester.tap(find.byKey(const Key('compile_mission_button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('mission_brief')), findsOneWidget);
    expect(find.textContaining('A recruiter for a backend role'), findsOneWidget);
    expect(find.textContaining('Tell me about yourself'), findsOneWidget);
    expect(find.byKey(const Key('launch_mission_button')), findsOneWidget);
  });

  testWidgets('shows an error snackbar when compile fails', (tester) async {
    final repo = _MockMissionRepo();
    when(
      () => repo.compile(
        sourceType: any(named: 'sourceType'),
        content: any(named: 'content'),
      ),
    ).thenThrow(Exception('down'));

    await _pump(tester, repo);
    await tester.enterText(
      find.byKey(const Key('mission_content')),
      'some text',
    );
    await tester.tap(find.byKey(const Key('compile_mission_button')));
    await tester.pumpAndSettle();

    expect(find.textContaining('Impossible de compiler'), findsOneWidget);
    expect(find.byKey(const Key('mission_brief')), findsNothing);
  });

  testWidgets('offers the five source types', (tester) async {
    await _pump(tester, _MockMissionRepo());
    for (final type in MissionSourceType.values) {
      expect(find.byKey(Key('source_${type.wire}')), findsOneWidget);
    }
  });
}

import 'package:apm/src/data/models/proof.dart';
import 'package:apm/src/data/repositories/proof_repository.dart';
import 'package:apm/src/ui/proof/view_model/proof_view_model.dart';
import 'package:apm/src/ui/proof/widgets/proof_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockRepo extends Mock implements ProofRepository {}

Proof _proof({List<String> resolved = const ['verb_tense'], List<String> worse = const []}) =>
    Proof(
      skill: 'job_interview',
      baselineSessionId: 1,
      latestSessionId: 2,
      baselineStartedAt: DateTime.utc(2026, 8, 1),
      latestStartedAt: DateTime.utc(2026, 8, 5),
      baselineCefr: 'A2',
      latestCefr: 'B1',
      resolved: resolved,
      newOrWorse: worse,
    );

Future<void> _pump(WidgetTester tester, ProofRepository repo) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [proofRepositoryProvider.overrideWithValue(repo)],
      child: const MaterialApp(home: ProofScreen(skill: 'job_interview')),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows the before/after CEFR and resolved errors', (tester) async {
    final repo = _MockRepo();
    when(() => repo.forSkill('job_interview')).thenAnswer((_) async => _proof());

    await _pump(tester, repo);

    expect(find.text('A2'), findsOneWidget); // before
    expect(find.text('B1'), findsOneWidget); // now
    expect(find.byKey(const Key('resolved_verb_tense')), findsOneWidget);
    expect(find.text('Temps du verbe'), findsOneWidget); // humanised label
  });

  testWidgets('surfaces regressions honestly', (tester) async {
    final repo = _MockRepo();
    when(() => repo.forSkill('job_interview')).thenAnswer(
      (_) async => _proof(resolved: const [], worse: const ['preposition']),
    );

    await _pump(tester, repo);

    expect(find.byKey(const Key('worse_preposition')), findsOneWidget);
    expect(find.textContaining('À surveiller'), findsOneWidget);
  });

  testWidgets('shows a "building" state when there is no proof yet', (tester) async {
    final repo = _MockRepo();
    when(() => repo.forSkill('job_interview')).thenAnswer((_) async => null);

    await _pump(tester, repo);

    expect(find.byKey(const Key('proof_empty')), findsOneWidget);
  });

  testWidgets('error state shows a message', (tester) async {
    final repo = _MockRepo();
    when(() => repo.forSkill('job_interview')).thenThrow(Exception('down'));

    await _pump(tester, repo);

    expect(find.byKey(const Key('proof_error')), findsOneWidget);
  });
}

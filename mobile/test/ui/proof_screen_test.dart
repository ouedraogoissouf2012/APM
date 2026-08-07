import 'dart:typed_data';

import 'package:apm/src/core/audio/audio_playback_service.dart';
import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:apm/src/data/models/mission.dart';
import 'package:apm/src/data/models/proof.dart';
import 'package:apm/src/data/repositories/proof_repository.dart';
import 'package:apm/src/ui/proof/view_model/proof_view_model.dart';
import 'package:apm/src/ui/proof/widgets/proof_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mocktail/mocktail.dart';

class _MockRepo extends Mock implements ProofRepository {}

/// Records which take byte-lengths were played, so the A/B test can assert the
/// baseline then the latest were played.
class _FakePlayback implements AudioPlaybackService {
  final List<int> playedLengths = [];
  @override
  Future<void> playClip(String audioB64, String mime) async {}
  @override
  Future<void> playBytes(Uint8List bytes, String mime) async => playedLengths.add(bytes.length);
  @override
  Future<void> stop() async {}
}

Mission _mission() => const Mission(
  id: 42,
  sourceType: 'topic',
  persona: 'A surprise interlocutor',
  goal: 'Handle a new situation',
  likelyQuestions: [],
);

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
      overrides: [
        proofRepositoryProvider.overrideWithValue(repo),
        // In-memory store so the screen never touches the file/path_provider store
        // (no platform channel in a unit test); the audible player stays hidden.
        voiceTakeStoreProvider.overrideWithValue(InMemoryVoiceTakeStore()),
      ],
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

  testWidgets('audible before/after: plays the first then the latest take (#199)',
      (tester) async {
    final repo = _MockRepo();
    when(() => repo.forSkill('job_interview')).thenAnswer((_) async => _proof());
    final store = InMemoryVoiceTakeStore();
    await store.saveTake('job_interview', Uint8List.fromList(const [1, 2, 3])); // baseline
    await store.saveTake('job_interview', Uint8List.fromList(const [4, 5, 6, 7])); // latest
    final playback = _FakePlayback();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          proofRepositoryProvider.overrideWithValue(repo),
          voiceTakeStoreProvider.overrideWithValue(store),
          audioPlaybackProvider.overrideWithValue(playback),
        ],
        child: const MaterialApp(home: ProofScreen(skill: 'job_interview')),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('audible_proof')), findsOneWidget);
    await tester.tap(find.byKey(const Key('play_baseline')));
    await tester.tap(find.byKey(const Key('play_latest')));
    await tester.pumpAndSettle();

    // Baseline (3 bytes) then latest (4 bytes) were played.
    expect(playback.playedLengths, [3, 4]);
  });

  testWidgets('audible before/after is hidden until there are two takes', (tester) async {
    final repo = _MockRepo();
    when(() => repo.forSkill('job_interview')).thenAnswer((_) async => _proof());
    final store = InMemoryVoiceTakeStore();
    await store.saveTake('job_interview', Uint8List.fromList(const [1, 2, 3])); // only baseline

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          proofRepositoryProvider.overrideWithValue(repo),
          voiceTakeStoreProvider.overrideWithValue(store),
        ],
        child: const MaterialApp(home: ProofScreen(skill: 'job_interview')),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('audible_proof')), findsNothing);
  });

  testWidgets('tapping "Tenter le transfert" compiles a challenge and launches it',
      (tester) async {
    final repo = _MockRepo();
    when(() => repo.forSkill('job_interview')).thenAnswer((_) async => _proof());
    when(
      () => repo.transferChallenge('job_interview'),
    ).thenAnswer((_) async => _mission());

    final router = GoRouter(
      initialLocation: '/proof/job_interview',
      routes: [
        GoRoute(
          path: '/proof/:skill',
          builder: (_, state) =>
              ProofScreen(skill: state.pathParameters['skill']!),
        ),
        GoRoute(
          path: '/conversation',
          builder: (_, _) => const Scaffold(body: Text('Conversation target')),
        ),
      ],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [proofRepositoryProvider.overrideWithValue(repo)],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('transfer_button')));
    await tester.pumpAndSettle();

    verify(() => repo.transferChallenge('job_interview')).called(1);
    expect(find.text('Conversation target'), findsOneWidget); // launched
  });
}

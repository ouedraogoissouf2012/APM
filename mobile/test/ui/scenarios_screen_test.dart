import 'package:apm/src/core/router/debounced_push.dart';
import 'package:apm/src/core/router/routes.dart';
import 'package:apm/src/ui/scenarios/widgets/scenarios_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

Future<void> _pump(WidgetTester tester) async {
  final router = GoRouter(
    initialLocation: Routes.scenarios,
    routes: [
      GoRoute(path: Routes.scenarios, builder: (_, _) => const ScenariosScreen()),
      GoRoute(
        path: Routes.proofPattern,
        builder: (_, _) => const Scaffold(body: Text('Proof target')),
      ),
    ],
  );
  await tester.pumpWidget(MaterialApp.router(routerConfig: router));
  await tester.pumpAndSettle();
}

void main() {
  // Shared, single-instance guard (#331) — see debounced_push.dart's own doc
  // comment on why tests must reset it. A FIXED clock also makes the
  // double-tap test below immune to real elapsed time on a slow CI runner.
  setUp(() => debugResetDebouncedPushGuard(DebouncedPushGuard(clock: () => DateTime(2026))));

  testWidgets('shows the free option and the guided scenarios', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: ScenariosScreen()));

    expect(find.byKey(const Key('free_conversation')), findsOneWidget);
    expect(find.text('At a restaurant'), findsOneWidget);
    expect(find.byKey(const Key('scenario_job_interview')), findsOneWidget);
  });

  testWidgets('the "Ma preuve" icon opens the proof screen for that scenario',
      (tester) async {
    await _pump(tester);
    await tester.tap(find.byKey(const Key('proof_job_interview')));
    await tester.pumpAndSettle();
    expect(find.text('Proof target'), findsOneWidget);
  });

  testWidgets('a rapid double-tap on "Ma preuve" pushes only once (#331)',
      (tester) async {
    await _pump(tester);
    final button = find.byKey(const Key('proof_job_interview'));
    await tester.tap(button);
    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(find.text('Proof target'), findsOneWidget);

    Navigator.of(tester.element(find.text('Proof target'))).pop();
    await tester.pumpAndSettle();

    expect(find.text('Proof target'), findsNothing);
    expect(find.byKey(const Key('scenario_job_interview')), findsOneWidget);
  });
}

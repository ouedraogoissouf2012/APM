import 'package:apm/src/core/router/debounced_push.dart';
import 'package:apm/src/core/router/routes.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/ui/learn/widgets/learn_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

Future<void> _pump(WidgetTester tester) async {
  final router = GoRouter(
    initialLocation: Routes.learn,
    routes: [
      GoRoute(path: Routes.learn, builder: (_, _) => const LearnScreen()),
      GoRoute(
        path: Routes.memory,
        builder: (_, _) => const Scaffold(body: Text('Memory target')),
      ),
      GoRoute(
        path: Routes.vocabulary,
        builder: (_, _) => const Scaffold(body: Text('Vocabulary target')),
      ),
      GoRoute(
        path: Routes.review,
        builder: (_, _) => const Scaffold(body: Text('Review target')),
      ),
    ],
  );
  await tester.pumpWidget(
    MaterialApp.router(theme: AppTheme.dark(), routerConfig: router),
  );
  await tester.pumpAndSettle();
}

void main() {
  // Shared, single-instance guard (#331) — reset before every test so a
  // route pushed by one test can't spuriously debounce the same route in
  // another (see debounced_push.dart's own doc comment). A FIXED clock also
  // makes the double-tap tests below immune to real elapsed time on a slow
  // CI runner.
  setUp(() => debugResetDebouncedPushGuard(DebouncedPushGuard(clock: () => DateTime(2026))));

  testWidgets('groups the three learning zones under one hub (#194)',
      (tester) async {
    await _pump(tester);
    expect(find.text('Apprendre'), findsOneWidget);
    expect(find.byKey(const Key('learn_memory')), findsOneWidget);
    expect(find.byKey(const Key('learn_vocabulary')), findsOneWidget);
    expect(find.byKey(const Key('learn_review')), findsOneWidget);
  });

  testWidgets('the memory card opens "ce que je sais de toi"', (tester) async {
    await _pump(tester);
    await tester.tap(find.byKey(const Key('learn_memory')));
    await tester.pumpAndSettle();
    expect(find.text('Memory target'), findsOneWidget);
  });

  testWidgets('the notebook card opens the vocabulary screen', (tester) async {
    await _pump(tester);
    await tester.tap(find.byKey(const Key('learn_vocabulary')));
    await tester.pumpAndSettle();
    expect(find.text('Vocabulary target'), findsOneWidget);
  });

  testWidgets('the review card opens the spaced review', (tester) async {
    await _pump(tester);
    await tester.tap(find.byKey(const Key('learn_review')));
    await tester.pumpAndSettle();
    expect(find.text('Review target'), findsOneWidget);
  });

  group('anti-double-tap on push navigation (#331)', () {
    testWidgets('a rapid double-tap on "ce que je sais de toi" pushes only once',
        (tester) async {
      await _pump(tester);
      final card = find.byKey(const Key('learn_memory'));
      await tester.tap(card);
      await tester.tap(card);
      await tester.pumpAndSettle();
      expect(find.text('Memory target'), findsOneWidget);

      Navigator.of(tester.element(find.text('Memory target'))).pop();
      await tester.pumpAndSettle();

      expect(find.text('Memory target'), findsNothing);
      expect(find.text('Apprendre'), findsOneWidget);
    });

    testWidgets('a rapid double-tap on "mon carnet" pushes only once',
        (tester) async {
      await _pump(tester);
      final card = find.byKey(const Key('learn_vocabulary'));
      await tester.tap(card);
      await tester.tap(card);
      await tester.pumpAndSettle();
      expect(find.text('Vocabulary target'), findsOneWidget);

      Navigator.of(tester.element(find.text('Vocabulary target'))).pop();
      await tester.pumpAndSettle();

      expect(find.text('Vocabulary target'), findsNothing);
      expect(find.text('Apprendre'), findsOneWidget);
    });

    testWidgets('a rapid double-tap on "à réviser" pushes only once',
        (tester) async {
      await _pump(tester);
      final card = find.byKey(const Key('learn_review'));
      await tester.tap(card);
      await tester.tap(card);
      await tester.pumpAndSettle();
      expect(find.text('Review target'), findsOneWidget);

      Navigator.of(tester.element(find.text('Review target'))).pop();
      await tester.pumpAndSettle();

      expect(find.text('Review target'), findsNothing);
      expect(find.text('Apprendre'), findsOneWidget);
    });
  });
}

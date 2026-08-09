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
  testWidgets('groups the three learning zones under one hub (#194)',
      (tester) async {
    await _pump(tester);
    expect(find.text('Apprendre'), findsOneWidget);
    expect(find.byKey(const Key('learn_memory')), findsOneWidget);
    expect(find.byKey(const Key('learn_vocabulary')), findsOneWidget);
    expect(find.byKey(const Key('learn_review')), findsOneWidget);
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
}

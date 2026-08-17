import 'package:apm/src/core/router/routes.dart';
import 'package:apm/src/core/ui/app_back_leading.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

void main() {
  testWidgets('pops when the stack has a previous route', (tester) async {
    final router = GoRouter(
      initialLocation: '/parent/child',
      routes: [
        GoRoute(path: Routes.home, builder: (_, _) => const Text('home')),
        GoRoute(
          path: '/parent',
          builder: (_, _) => const Scaffold(body: Text('parent')),
          routes: [
            GoRoute(
              path: 'child',
              builder: (_, _) => Scaffold(
                appBar: AppBar(leading: const AppBackLeading()),
                body: const Text('child'),
              ),
            ),
          ],
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('app_back')));
    await tester.pumpAndSettle();

    expect(find.text('parent'), findsOneWidget);
  });

  testWidgets('goes to fallback when there is nothing to pop', (tester) async {
    final router = GoRouter(
      initialLocation: '/alone',
      routes: [
        GoRoute(path: Routes.home, builder: (_, _) => const Text('home')),
        GoRoute(
          path: '/alone',
          builder: (_, _) => Scaffold(
            appBar: AppBar(leading: const AppBackLeading()),
            body: const Text('alone'),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('app_back')));
    await tester.pumpAndSettle();

    expect(find.text('home'), findsOneWidget);
  });
}

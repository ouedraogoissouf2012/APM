import 'package:apm/src/ui/onboarding/widgets/onboarding_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

void main() {
  testWidgets('shows the learning loop and navigates to auth screens', (
    tester,
  ) async {
    final router = GoRouter(
      initialLocation: '/onboarding',
      routes: [
        GoRoute(
          path: '/onboarding',
          builder: (_, _) => const OnboardingScreen(),
        ),
        GoRoute(
          path: '/register',
          builder: (_, _) => const Scaffold(body: Text('Register target')),
        ),
        GoRoute(
          path: '/login',
          builder: (_, _) => const Scaffold(body: Text('Login target')),
        ),
      ],
    );

    await tester.pumpWidget(MaterialApp.router(routerConfig: router));

    expect(find.text('Practice English with a clear loop'), findsOneWidget);
    expect(find.text('Profile'), findsOneWidget);
    expect(find.text('Scenario'), findsOneWidget);
    expect(find.text('Conversation'), findsOneWidget);
    expect(find.text('Debrief'), findsOneWidget);

    final registerButton = find.byKey(const Key('onboarding_register_button'));
    await tester.ensureVisible(registerButton);
    await tester.tap(registerButton);
    await tester.pumpAndSettle();
    expect(find.text('Register target'), findsOneWidget);

    router.go('/onboarding');
    await tester.pumpAndSettle();

    final loginButton = find.byKey(const Key('onboarding_login_button'));
    await tester.ensureVisible(loginButton);
    await tester.tap(loginButton);
    await tester.pumpAndSettle();
    expect(find.text('Login target'), findsOneWidget);
  });
}

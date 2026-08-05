import 'package:apm/src/core/router/routes.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/data/models/app_user.dart';
import 'package:apm/src/data/models/streak.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:apm/src/ui/home/view_model/streak_view_model.dart';
import 'package:apm/src/ui/home/widgets/home_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

class _StubAuth extends AuthViewModel {
  @override
  Future<AppUser?> build() async => const AppUser(
    id: 1,
    email: 'seven@apm.dev',
    nativeLanguage: 'fr',
    cefrLevel: 'A1',
    tier: 'free',
  );
}

Future<void> _pump(WidgetTester tester, {required Streak? streak}) async {
  final router = GoRouter(
    initialLocation: Routes.home,
    routes: [
      GoRoute(path: Routes.home, builder: (_, _) => const HomeScreen()),
    ],
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authViewModelProvider.overrideWith(_StubAuth.new),
        if (streak != null)
          streakProvider.overrideWith((ref) async => streak)
        else
          streakProvider.overrideWith((ref) async => throw Exception('none')),
      ],
      child: MaterialApp.router(theme: AppTheme.dark(), routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
}

Streak _streak(int days) => Streak(
  currentStreak: days,
  longestStreak: days,
  weeklyGoalMinutes: 30,
  minutesThisWeek: 12,
);

void main() {
  testWidgets('shows the streak pill with the day count', (tester) async {
    await _pump(tester, streak: _streak(7));
    expect(find.byKey(const Key('streak_pill')), findsOneWidget);
    expect(find.textContaining('7 jours'), findsOneWidget);
  });

  testWidgets('singular label for a one-day streak', (tester) async {
    await _pump(tester, streak: _streak(1));
    expect(find.textContaining('1 jour'), findsOneWidget);
    expect(find.textContaining('1 jours'), findsNothing);
  });

  testWidgets('hides the pill when there is no active streak', (tester) async {
    await _pump(tester, streak: _streak(0));
    expect(find.byKey(const Key('streak_pill')), findsNothing);
  });

  testWidgets('hides the pill when the streak fails to load', (tester) async {
    await _pump(tester, streak: null); // provider throws
    expect(find.byKey(const Key('streak_pill')), findsNothing);
  });
}

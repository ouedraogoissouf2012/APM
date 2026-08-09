import 'package:apm/src/core/router/routes.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/data/models/app_user.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:apm/src/ui/home/widgets/home_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

class _StubAuth extends AuthViewModel {
  _StubAuth(this._user);
  final AppUser? _user;
  bool loggedOut = false;

  @override
  Future<AppUser?> build() async => _user;

  @override
  Future<void> logout() async {
    loggedOut = true;
  }
}

const _user = AppUser(
  id: 1,
  email: 'seven@apm.dev',
  nativeLanguage: 'fr',
  cefrLevel: 'B1',
  tier: 'free',
);

Future<_StubAuth> _pump(WidgetTester tester, {AppUser? user = _user}) async {
  final stub = _StubAuth(user);
  final router = GoRouter(
    initialLocation: Routes.home,
    routes: [
      GoRoute(path: Routes.home, builder: (_, _) => const HomeScreen()),
      GoRoute(
        path: Routes.scenarios,
        builder: (_, _) => const Scaffold(body: Text('Scenarios target')),
      ),
      GoRoute(
        path: Routes.profile,
        builder: (_, _) => const Scaffold(body: Text('Profile target')),
      ),
      GoRoute(
        path: Routes.history,
        builder: (_, _) => const Scaffold(body: Text('History target')),
      ),
    ],
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: [authViewModelProvider.overrideWith(() => stub)],
      child: MaterialApp.router(theme: AppTheme.dark(), routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
  return stub;
}

void main() {
  testWidgets('greets the learner by name derived from their email',
      (tester) async {
    await _pump(tester);
    expect(find.textContaining('Seven'), findsOneWidget);
  });

  testWidgets('primary action starts a conversation (→ scenarios)',
      (tester) async {
    await _pump(tester);
    await tester.tap(find.byKey(const Key('start_conversation_button')));
    await tester.pumpAndSettle();
    expect(find.text('Scenarios target'), findsOneWidget);
  });

  testWidgets('bottom navigation exposes the four sections', (tester) async {
    await _pump(tester);
    expect(find.byKey(const Key('nav_talk')), findsOneWidget);
    expect(find.byKey(const Key('nav_learn')), findsOneWidget);
    expect(find.byKey(const Key('nav_progress')), findsOneWidget);
    expect(find.byKey(const Key('nav_profile')), findsOneWidget);
  });

  testWidgets('profile nav goes to the profile screen', (tester) async {
    await _pump(tester);
    await tester.tap(find.byKey(const Key('nav_profile')));
    await tester.pumpAndSettle();
    expect(find.text('Profile target'), findsOneWidget);
  });

  testWidgets('progress nav goes to history', (tester) async {
    await _pump(tester);
    await tester.tap(find.byKey(const Key('nav_progress')));
    await tester.pumpAndSettle();
    expect(find.text('History target'), findsOneWidget);
  });

  testWidgets('logout button signs the learner out', (tester) async {
    final stub = await _pump(tester);
    await tester.tap(find.byKey(const Key('logout_button')));
    await tester.pump();
    expect(stub.loggedOut, isTrue);
  });

  testWidgets('renders without a user without crashing', (tester) async {
    await _pump(tester, user: null);
    expect(find.byKey(const Key('start_conversation_button')), findsOneWidget);
  });
}

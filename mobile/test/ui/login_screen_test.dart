import 'package:apm/src/core/network/providers.dart';
import 'package:apm/src/data/models/app_user.dart';
import 'package:apm/src/data/repositories/auth_repository.dart';
import 'package:apm/src/data/repositories/runtime_config_repository.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:apm/src/ui/auth/widgets/login_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuthRepository extends Mock implements AuthRepository {}

void main() {
  testWidgets('entering credentials and tapping log in calls the repository', (
    tester,
  ) async {
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => null);
    when(
      () => repo.login(
        email: any(named: 'email'),
        password: any(named: 'password'),
      ),
    ).thenAnswer(
      (_) async => const AppUser(
        id: 1,
        email: 'a@b.com',
        nativeLanguage: 'fr',
        cefrLevel: 'A1',
        tier: 'free',
      ),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [authRepositoryProvider.overrideWithValue(repo)],
        child: const MaterialApp(home: LoginScreen()),
      ),
    );
    await tester.pump(); // resolve initial build

    await tester.enterText(find.byKey(const Key('email_field')), 'a@b.com');
    await tester.enterText(find.byKey(const Key('password_field')), 's3cret!');
    await tester.tap(find.byKey(const Key('login_button')));
    await tester.pump();

    verify(() => repo.login(email: 'a@b.com', password: 's3cret!')).called(1);
    expect(find.byKey(const Key('go_forgot_password')), findsNothing);
  });

  testWidgets('forgot link appears only when the mailer is live', (tester) async {
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => null);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authRepositoryProvider.overrideWithValue(repo),
          runtimeConfigProvider.overrideWith(
            (ref) async => const RuntimeConfig(
              demoMode: false,
              serverTts: false,
              passwordResetEnabled: true,
            ),
          ),
        ],
        child: const MaterialApp(home: LoginScreen()),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('go_forgot_password')), findsOneWidget);
  });
}

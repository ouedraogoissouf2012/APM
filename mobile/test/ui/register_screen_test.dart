import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/data/models/app_user.dart';
import 'package:apm/src/data/repositories/auth_repository.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:apm/src/ui/auth/widgets/register_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuthRepository extends Mock implements AuthRepository {}

void main() {
  testWidgets('valid form calls register with email, password and language', (
    tester,
  ) async {
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => null);
    when(
      () => repo.register(
        email: any(named: 'email'),
        password: any(named: 'password'),
        nativeLanguage: any(named: 'nativeLanguage'),
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
        child: MaterialApp(theme: AppTheme.dark(), home: const RegisterScreen()),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byKey(const Key('email_field')), 'a@b.com');
    await tester.enterText(find.byKey(const Key('password_field')), 's3cret!!');
    await tester.enterText(
      find.byKey(const Key('confirm_password_field')),
      's3cret!!',
    );
    await tester.ensureVisible(find.byKey(const Key('register_button')));
    await tester.tap(find.byKey(const Key('register_button')));
    await tester.pump();

    verify(
      () => repo.register(
        email: 'a@b.com',
        password: 's3cret!!',
        nativeLanguage: 'fr',
      ),
    ).called(1);
  });

  testWidgets('mismatched passwords do not call the repository', (
    tester,
  ) async {
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => null);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [authRepositoryProvider.overrideWithValue(repo)],
        child: MaterialApp(theme: AppTheme.dark(), home: const RegisterScreen()),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byKey(const Key('email_field')), 'a@b.com');
    await tester.enterText(find.byKey(const Key('password_field')), 's3cret!!');
    await tester.enterText(
      find.byKey(const Key('confirm_password_field')),
      'otherpass',
    );
    await tester.ensureVisible(find.byKey(const Key('register_button')));
    await tester.tap(find.byKey(const Key('register_button')));
    await tester.pump();

    verifyNever(
      () => repo.register(
        email: any(named: 'email'),
        password: any(named: 'password'),
        nativeLanguage: any(named: 'nativeLanguage'),
      ),
    );
  });
}

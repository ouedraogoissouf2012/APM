import 'package:apm/src/core/network/providers.dart';
import 'package:apm/src/data/repositories/auth_repository.dart';
import 'package:apm/src/data/repositories/runtime_config_repository.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:apm/src/ui/auth/widgets/forgot_password_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuthRepository extends Mock implements AuthRepository {}

void main() {
  testWidgets('sans mailer : réinitialisation indisponible', (tester) async {
    final repo = _MockAuthRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [authRepositoryProvider.overrideWithValue(repo)],
        child: const MaterialApp(home: ForgotPasswordScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('forgot_unavailable')), findsOneWidget);
    expect(find.byKey(const Key('forgot_submit')), findsNothing);
    expect(find.textContaining('email is sent'), findsNothing);
  });

  testWidgets('mailer live : copy honnête, pas « email is sent »', (tester) async {
    final repo = _MockAuthRepository();
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
        child: const MaterialApp(home: ForgotPasswordScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('forgot_honest')), findsOneWidget);
    expect(find.textContaining('Si un compte existe'), findsOneWidget);
    expect(find.textContaining('email is sent'), findsNothing);
    expect(find.byKey(const Key('forgot_submit')), findsOneWidget);
  });
}

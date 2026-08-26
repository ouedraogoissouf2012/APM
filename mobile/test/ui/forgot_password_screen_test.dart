import 'package:apm/src/data/repositories/auth_repository.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:apm/src/ui/auth/widgets/forgot_password_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuthRepository extends Mock implements AuthRepository {}

void main() {
  testWidgets('forgot_honest est en français et n’annonce pas d’e-mail envoyé', (
    tester,
  ) async {
    final repo = _MockAuthRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [authRepositoryProvider.overrideWithValue(repo)],
        child: const MaterialApp(home: ForgotPasswordScreen()),
      ),
    );

    expect(find.byKey(const Key('forgot_honest')), findsOneWidget);
    expect(find.textContaining('Aucun e-mail'), findsOneWidget);
    expect(find.textContaining('email is sent'), findsNothing);
    expect(find.textContaining('retrieve in dev'), findsNothing);
  });
}

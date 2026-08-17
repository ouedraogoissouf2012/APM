import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
import '../../../core/ui/app_back_leading.dart';
import '../view_model/auth_view_model.dart';
import 'auth_fields.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authViewModelProvider);
    return Scaffold(
      appBar: AppBar(
        leading: const AppBackLeading(fallback: Routes.onboarding),
        title: const Text('Log in'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            AuthFields(
              email: _email,
              password: _password,
              hasError: auth.hasError,
              errorLabel: 'Login failed',
              errorKey: const Key('login_error'),
            ),
            FilledButton(
              key: const Key('login_button'),
              onPressed: auth.isLoading
                  ? null
                  : () => ref
                        .read(authViewModelProvider.notifier)
                        .login(email: _email.text, password: _password.text),
              child: auth.isLoading
                  ? const CircularProgressIndicator()
                  : const Text('Log in'),
            ),
            TextButton(
              key: const Key('go_forgot_password'),
              onPressed: () => context.go(Routes.forgotPassword),
              child: const Text('Forgot password?'),
            ),
            TextButton(
              key: const Key('go_register'),
              onPressed: () => context.go(Routes.register),
              child: const Text('Create an account'),
            ),
          ],
        ),
      ),
    );
  }
}

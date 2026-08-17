import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
import '../../../core/ui/app_back_leading.dart';
import '../view_model/auth_view_model.dart';
import 'auth_fields.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
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
        title: const Text('Create account'),
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
              errorLabel: 'Registration failed',
              errorKey: const Key('register_error'),
            ),
            FilledButton(
              key: const Key('register_button'),
              onPressed: auth.isLoading
                  ? null
                  : () => ref
                        .read(authViewModelProvider.notifier)
                        .register(email: _email.text, password: _password.text),
              child: const Text('Create account'),
            ),
            TextButton(
              key: const Key('go_login'),
              onPressed: () => context.go(Routes.login),
              child: const Text('I already have an account'),
            ),
          ],
        ),
      ),
    );
  }
}

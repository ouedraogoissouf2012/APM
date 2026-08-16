import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/router/routes.dart';
import '../view_model/auth_view_model.dart';

class ForgotPasswordScreen extends ConsumerStatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  ConsumerState<ForgotPasswordScreen> createState() =>
      _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends ConsumerState<ForgotPasswordScreen> {
  final _email = TextEditingController();
  var _sending = false;
  var _done = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      await ref
          .read(authRepositoryProvider)
          .requestPasswordReset(email: _email.text.trim());
      if (mounted) setState(() => _done = true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'Request failed');
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Forgot password')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (_done)
              const Text(
                key: Key('forgot_sent'),
                'If an account exists for that email, follow the reset steps.',
              )
            else ...[
              TextField(
                key: const Key('forgot_email'),
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                decoration: const InputDecoration(labelText: 'Email'),
              ),
              if (_error != null) Text(_error!, key: const Key('forgot_error')),
              FilledButton(
                key: const Key('forgot_submit'),
                onPressed: _sending ? null : _submit,
                child: _sending
                    ? const CircularProgressIndicator()
                    : const Text('Send reset'),
              ),
            ],
            TextButton(
              key: const Key('forgot_go_reset'),
              onPressed: () => context.go(Routes.resetPassword),
              child: const Text('I have a reset token'),
            ),
            TextButton(
              onPressed: () => context.go(Routes.login),
              child: const Text('Back to log in'),
            ),
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/router/routes.dart';
import '../../../core/ui/app_back_leading.dart';
import '../view_model/auth_view_model.dart';

class ResetPasswordScreen extends ConsumerStatefulWidget {
  const ResetPasswordScreen({super.key});

  @override
  ConsumerState<ResetPasswordScreen> createState() =>
      _ResetPasswordScreenState();
}

class _ResetPasswordScreenState extends ConsumerState<ResetPasswordScreen> {
  // Token is pasted, never taken from ?token= (logs / Referer).
  final _token = TextEditingController();
  final _password = TextEditingController();
  var _sending = false;
  var _done = false;
  String? _error;

  @override
  void dispose() {
    _token.dispose();
    _password.dispose();
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
          .resetPassword(
            token: _token.text.trim(),
            newPassword: _password.text,
          );
      if (mounted) setState(() => _done = true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'Reset failed');
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const AppBackLeading(fallback: Routes.login),
        title: const Text('Reset password'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (_done)
              FilledButton(
                key: const Key('reset_go_login'),
                onPressed: () => context.go(Routes.login),
                child: const Text('Password updated. Log in'),
              )
            else ...[
              TextField(
                key: const Key('reset_token'),
                controller: _token,
                decoration: const InputDecoration(labelText: 'Reset token'),
              ),
              TextField(
                key: const Key('reset_password'),
                controller: _password,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'New password'),
              ),
              if (_error != null) Text(_error!, key: const Key('reset_error')),
              FilledButton(
                key: const Key('reset_submit'),
                onPressed: _sending ? null : _submit,
                child: _sending
                    ? const CircularProgressIndicator()
                    : const Text('Update password'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

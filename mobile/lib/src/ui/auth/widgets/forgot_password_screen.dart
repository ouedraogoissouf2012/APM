import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/network/providers.dart';
import '../../../core/router/routes.dart';
import '../../../core/ui/app_back_leading.dart';
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
      if (mounted) setState(() => _error = 'La demande a échoué');
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final resetOn =
        ref.watch(runtimeConfigProvider).value?.passwordResetEnabled ?? false;
    return Scaffold(
      appBar: AppBar(
        leading: const AppBackLeading(fallback: Routes.login),
        title: const Text('Mot de passe oublié'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (!resetOn)
              const Text(
                key: Key('forgot_unavailable'),
                'La réinitialisation par e-mail n’est pas encore disponible.',
              )
            else ...[
              const Text(
                key: Key('forgot_honest'),
                'Si un compte existe pour cet e-mail, un message part '
                'avec un jeton. Colle-le à l’écran suivant. '
                'Aucun lien magique n’est envoyé.',
              ),
              const SizedBox(height: 16),
              if (_done)
                const Text(
                  key: Key('forgot_sent'),
                  'Si un compte existe, regarde tes e-mails puis colle le jeton.',
                )
              else ...[
                TextField(
                  key: const Key('forgot_email'),
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  autocorrect: false,
                  decoration: const InputDecoration(labelText: 'E-mail'),
                ),
                if (_error != null)
                  Text(_error!, key: const Key('forgot_error')),
                FilledButton(
                  key: const Key('forgot_submit'),
                  onPressed: _sending ? null : _submit,
                  child: _sending
                      ? const CircularProgressIndicator()
                      : const Text('Envoyer le jeton'),
                ),
              ],
              TextButton(
                key: const Key('forgot_go_reset'),
                onPressed: () => context.go(Routes.resetPassword),
                child: const Text('J’ai un jeton de réinitialisation'),
              ),
            ],
            TextButton(
              onPressed: () => context.go(Routes.login),
              child: const Text('Retour à la connexion'),
            ),
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/router/routes.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/ui/app_back_leading.dart';
import '../../../design_system/atoms/overline_text.dart';
import '../view_model/auth_view_model.dart';

const _languages = <(String code, String label)>[
  ('fr', 'Français'),
  ('en', 'English'),
  ('es', 'Español'),
  ('de', 'Deutsch'),
  ('it', 'Italiano'),
  ('pt', 'Português'),
  ('ar', 'العربية'),
  ('zh', '中文'),
];

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  var _language = 'fr';
  var _hidePassword = true;
  var _hideConfirm = true;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  String? _emailError(String? value) {
    final v = value?.trim() ?? '';
    if (v.isEmpty) return 'Entre ton email.';
    if (!v.contains('@') || !v.contains('.'))
      return 'Cet email ne semble pas valide.';
    return null;
  }

  String? _passwordError(String? value) {
    final v = value ?? '';
    if (v.length < 8) return 'Au moins 8 caractères.';
    return null;
  }

  String? _confirmError(String? value) {
    if (value != _password.text)
      return 'Les mots de passe ne correspondent pas.';
    return null;
  }

  int get _strength {
    final p = _password.text;
    var score = 0;
    if (p.length >= 8) score++;
    if (p.length >= 12) score++;
    if (RegExp(r'[A-Z]').hasMatch(p) && RegExp(r'[a-z]').hasMatch(p)) score++;
    if (RegExp(r'\d').hasMatch(p)) score++;
    if (RegExp(r'[^A-Za-z0-9]').hasMatch(p)) score++;
    return score.clamp(0, 4);
  }

  Future<void> _submit() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    await ref
        .read(authViewModelProvider.notifier)
        .register(
          email: _email.text.trim(),
          password: _password.text,
          nativeLanguage: _language,
        );
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authViewModelProvider);
    final colors = context.colors;
    final apiError = auth.hasError ? _friendlyError(auth.error) : null;

    return Scaffold(
      appBar: AppBar(
        leading: const AppBackLeading(fallback: Routes.onboarding),
        title: const Text('Créer un compte'),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'Parle anglais, vraiment.',
                      style: AppType.displayLg(colors.textPrimary),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Un email, un mot de passe, et on commence. '
                      'Le niveau se règle après, en parlant.',
                      style: AppType.body(colors.textSecondary),
                    ),
                    const SizedBox(height: 28),
                    const OverlineText('ton compte'),
                    const SizedBox(height: 12),
                    TextFormField(
                      key: const Key('email_field'),
                      controller: _email,
                      keyboardType: TextInputType.emailAddress,
                      autofillHints: const [AutofillHints.email],
                      textInputAction: TextInputAction.next,
                      autocorrect: false,
                      validator: _emailError,
                      decoration: const InputDecoration(
                        labelText: 'Email',
                        hintText: 'toi@email.com',
                        prefixIcon: Icon(Icons.mail_outline),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      key: const Key('password_field'),
                      controller: _password,
                      obscureText: _hidePassword,
                      autofillHints: const [AutofillHints.newPassword],
                      textInputAction: TextInputAction.next,
                      onChanged: (_) => setState(() {}),
                      validator: _passwordError,
                      decoration: InputDecoration(
                        labelText: 'Mot de passe',
                        hintText: '8 caractères minimum',
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          key: const Key('toggle_password'),
                          tooltip: _hidePassword ? 'Afficher' : 'Masquer',
                          icon: Icon(
                            _hidePassword
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                          onPressed: () =>
                              setState(() => _hidePassword = !_hidePassword),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    _PasswordStrength(score: _strength),
                    const SizedBox(height: 12),
                    TextFormField(
                      key: const Key('confirm_password_field'),
                      controller: _confirm,
                      obscureText: _hideConfirm,
                      autofillHints: const [AutofillHints.newPassword],
                      textInputAction: TextInputAction.next,
                      validator: _confirmError,
                      decoration: InputDecoration(
                        labelText: 'Confirme le mot de passe',
                        prefixIcon: const Icon(Icons.lock_reset_outlined),
                        suffixIcon: IconButton(
                          tooltip: _hideConfirm ? 'Afficher' : 'Masquer',
                          icon: Icon(
                            _hideConfirm
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                          onPressed: () =>
                              setState(() => _hideConfirm = !_hideConfirm),
                        ),
                      ),
                    ),
                    const SizedBox(height: 20),
                    const OverlineText('tu parles surtout'),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      key: const Key('native_language_field'),
                      initialValue: _language,
                      decoration: const InputDecoration(
                        labelText: 'Langue maternelle',
                        prefixIcon: Icon(Icons.translate_outlined),
                      ),
                      items: [
                        for (final (code, label) in _languages)
                          DropdownMenuItem(value: code, child: Text(label)),
                      ],
                      onChanged: (v) {
                        if (v != null) setState(() => _language = v);
                      },
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Ça aide l’assistant à t’expliquer en français (ou dans ta langue).',
                      style: AppType.label(colors.textMuted),
                    ),
                    if (apiError != null) ...[
                      const SizedBox(height: 16),
                      Text(
                        apiError,
                        key: const Key('register_error'),
                        style: AppType.body(colors.accent),
                      ),
                    ],
                    const SizedBox(height: 24),
                    FilledButton(
                      key: const Key('register_button'),
                      onPressed: auth.isLoading ? null : _submit,
                      child: auth.isLoading
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Créer mon compte'),
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      key: const Key('go_login'),
                      onPressed: () => context.go(Routes.login),
                      child: const Text('J’ai déjà un compte'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  String _friendlyError(Object? error) {
    if (error is ApiException) {
      final m = error.message.toLowerCase();
      if (m.contains('already') || m.contains('exists') || m.contains('409')) {
        return 'Cet email a déjà un compte. Connecte-toi plutôt.';
      }
      if (error.message.isNotEmpty) return error.message;
    }
    return 'Impossible de créer le compte. Réessaie.';
  }
}

class _PasswordStrength extends StatelessWidget {
  const _PasswordStrength({required this.score});

  final int score;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final labels = [
      'Trop court',
      'Fragile',
      'Correct',
      'Solide',
      'Très solide',
    ];
    final barColor = switch (score) {
      0 => colors.borderStrong,
      1 => colors.accent,
      2 => colors.correction,
      _ => colors.positive,
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            for (var i = 0; i < 4; i++)
              Expanded(
                child: Container(
                  height: 4,
                  margin: EdgeInsets.only(right: i == 3 ? 0 : 4),
                  decoration: BoxDecoration(
                    color: i < score ? barColor : colors.border,
                    borderRadius: BorderRadius.circular(99),
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 6),
        Text(labels[score], style: AppType.label(colors.textMuted)),
      ],
    );
  }
}

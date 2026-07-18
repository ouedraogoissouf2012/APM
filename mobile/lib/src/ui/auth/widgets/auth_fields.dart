import 'package:flutter/material.dart';

/// The email/password fields + error line shared by the login and register
/// screens (they were near-identical copies before).
class AuthFields extends StatelessWidget {
  const AuthFields({
    super.key,
    required this.email,
    required this.password,
    required this.hasError,
    required this.errorLabel,
    required this.errorKey,
  });

  final TextEditingController email;
  final TextEditingController password;
  final bool hasError;
  final String errorLabel;
  final Key errorKey;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        TextField(
          key: const Key('email_field'),
          controller: email,
          decoration: const InputDecoration(labelText: 'Email'),
        ),
        TextField(
          key: const Key('password_field'),
          controller: password,
          obscureText: true,
          decoration: const InputDecoration(labelText: 'Password'),
        ),
        const SizedBox(height: 16),
        if (hasError)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              errorLabel,
              key: errorKey,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
      ],
    );
  }
}

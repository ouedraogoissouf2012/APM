import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
class OnboardingScreen extends StatelessWidget {
  const OnboardingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 520),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(
                    Icons.record_voice_over,
                    size: 48,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(height: 24),
                  Text(
                    'Practice English with a clear loop',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Set your profile, pick a scenario, speak, then review your debrief and history.',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 32),
                  const _OnboardingStep(
                    icon: Icons.person_outline,
                    title: 'Profile',
                    subtitle: 'Keep your level and learning context ready.',
                  ),
                  const _OnboardingStep(
                    icon: Icons.forum_outlined,
                    title: 'Scenario',
                    subtitle: 'Choose a guided situation or free practice.',
                  ),
                  const _OnboardingStep(
                    icon: Icons.mic_none,
                    title: 'Conversation',
                    subtitle: 'Speak turn by turn and keep the flow simple.',
                  ),
                  const _OnboardingStep(
                    icon: Icons.insights_outlined,
                    title: 'Debrief',
                    subtitle: 'Review errors, progress, and session history.',
                  ),
                  const SizedBox(height: 32),
                  FilledButton.icon(
                    key: const Key('onboarding_register_button'),
                    onPressed: () => context.go(Routes.register),
                    icon: const Icon(Icons.person_add_alt),
                    label: const Text('Create account'),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    key: const Key('onboarding_login_button'),
                    onPressed: () => context.go(Routes.login),
                    icon: const Icon(Icons.login),
                    label: const Text('Log in'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _OnboardingStep extends StatelessWidget {
  const _OnboardingStep({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: theme.colorScheme.primary),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

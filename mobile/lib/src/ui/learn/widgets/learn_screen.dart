import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
import '../../../core/theme/app_theme.dart';
import '../../../design_system/atoms/overline_text.dart';

/// "Apprendre" — the learning hub (#194). Groups the tools that used to be
/// buried as list tiles under the profile settings form (the tracked "dumping
/// ground" debt): the assistant's memory, the vocabulary notebook, and the
/// spaced review. Giving them one discoverable home — reachable from the bottom
/// nav — is the whole point of this screen; the profile goes back to pure
/// settings.
class LearnScreen extends StatelessWidget {
  const LearnScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Scaffold(
      appBar: AppBar(
        title: Text('Apprendre', style: AppType.displayMd(colors.textPrimary)),
      ),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          const OverlineText('tes outils'),
          const SizedBox(height: AppSpacing.md),
          _LearnCard(
            navKey: const Key('learn_memory'),
            icon: Icons.psychology_outlined,
            title: 'Ce que je sais de toi',
            subtitle: 'Voir et éditer la mémoire de l’assistant',
            onTap: () => context.push(Routes.memory),
          ),
          const SizedBox(height: AppSpacing.sm),
          _LearnCard(
            navKey: const Key('learn_vocabulary'),
            icon: Icons.menu_book_outlined,
            title: 'Mon carnet',
            subtitle: 'Les mots vus en session, à réviser',
            onTap: () => context.push(Routes.vocabulary),
          ),
          const SizedBox(height: AppSpacing.sm),
          _LearnCard(
            navKey: const Key('learn_review'),
            icon: Icons.repeat,
            title: 'À réviser',
            subtitle: 'Tes fautes récurrentes, au bon moment',
            onTap: () => context.push(Routes.review),
          ),
        ],
      ),
    );
  }
}

/// One tappable learning zone: leading icon, title, subtitle, chevron — the same
/// visual language as the debrief's "next steps" cards, on a bordered surface.
class _LearnCard extends StatelessWidget {
  const _LearnCard({
    required this.navKey,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final Key navKey;
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return InkWell(
      key: navKey,
      onTap: onTap,
      borderRadius: BorderRadius.circular(AppRadius.hero),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(AppSpacing.lg),
        decoration: BoxDecoration(
          color: colors.surface,
          borderRadius: BorderRadius.circular(AppRadius.hero),
          border: Border.all(color: colors.border, width: AppStroke.hairline),
        ),
        child: Row(
          children: [
            Icon(icon, color: colors.accent),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: AppType.body(colors.textPrimary)),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    subtitle,
                    style: AppType.label(colors.textSecondary).copyWith(fontSize: 13),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right, color: colors.textMuted),
          ],
        ),
      ),
    );
  }
}

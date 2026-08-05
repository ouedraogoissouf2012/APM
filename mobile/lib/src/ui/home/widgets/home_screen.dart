import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
import '../../../core/theme/app_theme.dart';
import '../../../design_system/atoms/overline_text.dart';
import '../../auth/view_model/auth_view_model.dart';
import '../view_model/streak_view_model.dart';
import 'home_greeting.dart';

/// Home — DESIGN_SPEC §6.3. Editorial greeting in Fraunces, a clay "resume"
/// card, and a bottom navigation of four sections. The greeting name and
/// time-of-day come from pure helpers ([displayNameFromEmail]/[greetingForHour])
/// so the widget stays declarative.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key, this.clock});

  /// Injectable clock for deterministic testing; defaults to now.
  final DateTime Function()? clock;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authViewModelProvider).value;
    final colors = context.colors;
    final now = (clock ?? DateTime.now)();
    final name = displayNameFromEmail(user?.email);

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _TopRow(onLogout: () {
                ref.read(authViewModelProvider.notifier).logout();
              }),
              const SizedBox(height: AppSpacing.xl),
              _Greeting(greeting: greetingForHour(now.hour), name: name),
              const SizedBox(height: AppSpacing.sm),
              const _StreakPill(),
              const SizedBox(height: AppSpacing.lg),
              _ResumeCard(
                onTap: () => context.go(Routes.scenarios),
              ),
              const SizedBox(height: AppSpacing.md),
              _DrillCard(
                key: const Key('start_echo_button'),
                overline: 'entraîne ton accent',
                title: 'Mode Écho',
                icon: Icons.graphic_eq,
                onTap: () => context.go(Routes.echo),
              ),
              const SizedBox(height: AppSpacing.md),
              _DrillCard(
                key: const Key('start_minimal_pairs_button'),
                overline: 'sons qui piègent',
                title: 'Paires minimales',
                icon: Icons.hearing,
                onTap: () => context.go(Routes.minimalPairs),
              ),
              const Spacer(),
            ],
          ),
        ),
      ),
      bottomNavigationBar: _HomeNavBar(colors: colors),
    );
  }
}

class _TopRow extends StatelessWidget {
  const _TopRow({required this.onLogout});

  final VoidCallback onLogout;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: IconButton(
        key: const Key('logout_button'),
        icon: const Icon(Icons.logout),
        color: context.colors.textMuted,
        tooltip: 'Se déconnecter',
        onPressed: onLogout,
      ),
    );
  }
}

/// "Good evening, Seven." — greeting in Fraunces, the name in italic clay.
class _Greeting extends StatelessWidget {
  const _Greeting({required this.greeting, required this.name});

  final String greeting;
  final String name;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    if (name.isEmpty) {
      return Text(greeting, style: AppType.displayLg(colors.textPrimary));
    }
    return Text.rich(
      TextSpan(
        style: AppType.displayLg(colors.textPrimary),
        children: [
          TextSpan(text: '$greeting, '),
          TextSpan(
            text: '$name.',
            style: AppType.displayItalic(colors.accent, fontSize: 28),
          ),
        ],
      ),
    );
  }
}

/// The clay "resume" card with decorative circles overflowing top-right,
/// clipped by the border radius (DESIGN_SPEC §4/§6.3).
class _ResumeCard extends StatelessWidget {
  const _ResumeCard({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return GestureDetector(
      key: const Key('start_conversation_button'),
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppRadius.hero),
        child: Container(
          height: 140,
          width: double.infinity,
          color: colors.accent,
          child: Stack(
            children: [
              // Decorative circles overflowing top-right.
              Positioned(
                right: -30,
                top: -40,
                child: _circle(96, colors.accentSoft),
              ),
              Positioned(
                right: 24,
                top: -56,
                child: _circle(72, colors.accentFaint),
              ),
              Padding(
                padding: const EdgeInsets.all(AppSpacing.xl),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    OverlineText('reprendre', color: colors.onAccent),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      'Commencer une conversation',
                      style: AppType.displayMd(colors.onAccent),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _circle(double size, Color color) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(shape: BoxShape.circle, color: color),
      );
}

/// A secondary practice-mode card (Écho, Paires minimales, ...): a surface card
/// with an overline, a title, a leading icon and a chevron.
class _DrillCard extends StatelessWidget {
  const _DrillCard({
    super.key,
    required this.overline,
    required this.title,
    required this.icon,
    required this.onTap,
  });

  final String overline;
  final String title;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(AppSpacing.lg),
        decoration: BoxDecoration(
          color: colors.surfaceAlt,
          borderRadius: BorderRadius.circular(AppRadius.card),
          border: Border.all(color: colors.border),
        ),
        child: Row(
          children: [
            Icon(icon, color: colors.accent),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  OverlineText(overline, color: colors.textMuted),
                  const SizedBox(height: AppSpacing.xs),
                  Text(title, style: AppType.body(colors.textPrimary)),
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

/// Bottom navigation — four sections (DESIGN_SPEC §6.3). "Parler" active.
///
/// The Memory screen does not exist yet; its tab routes home for now rather
/// than to a dead link — it will point to /memory once that screen lands.
class _HomeNavBar extends StatelessWidget {
  const _HomeNavBar({required this.colors});

  final AppSemanticColors colors;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: colors.backgroundDeep,
        border: Border(
          top: BorderSide(color: colors.border, width: AppStroke.hairline),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _NavItem(
              navKey: const Key('nav_talk'),
              icon: Icons.mic,
              label: 'Parler',
              active: true,
              color: colors.accent,
              onTap: () => context.go(Routes.scenarios),
            ),
            _NavItem(
              navKey: const Key('nav_memory'),
              icon: Icons.favorite_border,
              label: 'Mémoire',
              color: colors.textMuted,
              onTap: () => context.go(Routes.home),
            ),
            _NavItem(
              navKey: const Key('nav_progress'),
              icon: Icons.insights_outlined,
              label: 'Progrès',
              color: colors.textMuted,
              onTap: () => context.go(Routes.history),
            ),
            _NavItem(
              navKey: const Key('nav_profile'),
              icon: Icons.person_outline,
              label: 'Profil',
              color: colors.textMuted,
              onTap: () => context.go(Routes.profile),
            ),
          ],
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.navKey,
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
    this.active = false,
  });

  final Key navKey;
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  final bool active;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      key: navKey,
      onTap: onTap,
      borderRadius: BorderRadius.circular(AppRadius.chip),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(height: AppSpacing.xs),
            Text(label, style: AppType.label(color).copyWith(fontSize: 11)),
          ],
        ),
      ),
    );
  }
}

/// Streak pill under the greeting (DESIGN_SPEC §6): "🔥 N jours". Renders nothing
/// when there's no active streak yet, so it never adds empty space to the Home.
class _StreakPill extends ConsumerWidget {
  const _StreakPill();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final streak = ref.watch(streakProvider);
    final days = streak.value?.currentStreak ?? 0;
    if (days <= 0) return const SizedBox.shrink();

    final colors = context.colors;
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        key: const Key('streak_pill'),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: colors.surface,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          '🔥 $days ${days == 1 ? 'jour' : 'jours'}',
          style: Theme.of(context).textTheme.labelLarge,
        ),
      ),
    );
  }
}

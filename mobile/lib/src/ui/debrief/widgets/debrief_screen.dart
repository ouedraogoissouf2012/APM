import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/models/debrief.dart';
import '../../../design_system/atoms/overline_text.dart';
import '../view_model/debrief_view_model.dart';
import 'pronunciation_map.dart';

/// End-of-session debrief — DESIGN_SPEC §5.5 / §7. Rendered on the **cream**
/// (light) surface: a deliberate narrative inversion. The conversation happens
/// in the dark "tunnel"; the learner steps into the light to read their debrief.
///
/// The whole subtree is wrapped in [AppTheme.light] so every design-system
/// widget picks up the cream roles without any per-widget branching.
class DebriefScreen extends ConsumerWidget {
  const DebriefScreen({super.key, required this.sessionId});

  final int sessionId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(debriefProvider(sessionId));
    return Theme(
      data: AppTheme.light(),
      child: Builder(
        builder: (context) {
          final colors = context.colors;
          return Scaffold(
            backgroundColor: colors.background,
            appBar: AppBar(
              backgroundColor: colors.background,
              title: Text('Ton bilan', style: AppType.displayMd(colors.textPrimary)),
              actions: [
                IconButton(
                  key: const Key('debrief_home_button'),
                  icon: const Icon(Icons.home_outlined),
                  color: colors.textSecondary,
                  onPressed: () => context.go(Routes.home),
                ),
              ],
            ),
            body: async.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (_, _) => Center(
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.xl),
                  child: Text(
                    "Impossible de charger ton bilan.",
                    key: const Key('debrief_error'),
                    style: AppType.body(colors.textSecondary),
                  ),
                ),
              ),
              data: (debrief) => _DebriefBody(debrief: debrief),
            ),
          );
        },
      ),
    );
  }
}

class _DebriefBody extends StatelessWidget {
  const _DebriefBody({required this.debrief});

  final Debrief debrief;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        _ScoreCard(cefr: debrief.cefrEstimate),
        if (debrief.summary.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.xl),
          _WhatWorked(summary: debrief.summary),
        ],
        if (debrief.pronunciationScores.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.xl),
          const OverlineText('prononciation'),
          const SizedBox(height: AppSpacing.md),
          PronunciationMap(scores: debrief.pronunciationScores),
        ],
        const SizedBox(height: AppSpacing.xl),
        _ToReview(errors: debrief.errors),
        const SizedBox(height: AppSpacing.xxl),
      ],
    );
  }
}

/// Hero card: the CEFR level in large Fraunces. Honest metric — the model has
/// no 0-100 score, so we show the estimated level rather than inventing one.
class _ScoreCard extends StatelessWidget {
  const _ScoreCard({required this.cefr});

  final String cefr;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const OverlineText('niveau estimé'),
          const SizedBox(height: AppSpacing.sm),
          Text(
            cefr,
            key: const Key('cefr_estimate'),
            style: AppType.displayXl(colors.textPrimary),
          ),
        ],
      ),
    );
  }
}

class _WhatWorked extends StatelessWidget {
  const _WhatWorked({required this.summary});

  final String summary;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        OverlineText('ce qui a marché', color: colors.positive),
        const SizedBox(height: AppSpacing.md),
        Text(summary, style: AppType.body(colors.textPrimary)),
      ],
    );
  }
}

/// "À reprendre" — corrections. The error is never red: struck original in a
/// muted tone, the fix in Fraunces, the rule beneath.
class _ToReview extends StatelessWidget {
  const _ToReview({required this.errors});

  final List<DebriefError> errors;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        OverlineText('à reprendre', color: colors.accent),
        const SizedBox(height: AppSpacing.md),
        if (errors.isEmpty)
          Text(
            "Rien à corriger — beau travail !",
            key: const Key('debrief_no_errors'),
            style: AppType.body(colors.textPrimary),
          )
        else
          ...errors.map((e) => Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.md),
                child: _CorrectionPanel(error: e),
              )),
      ],
    );
  }
}

class _CorrectionPanel extends StatelessWidget {
  const _CorrectionPanel({required this.error});

  final DebriefError error;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (error.errorType.isNotEmpty) ...[
            OverlineText(
              error.errorType.replaceAll('_', ' '),
              color: colors.textMuted,
            ),
            const SizedBox(height: AppSpacing.sm),
          ],
          Text(
            error.original,
            style: AppType.body(colors.textFaint).copyWith(
              decoration: TextDecoration.lineThrough,
              decorationColor: colors.textFaint,
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(error.correction, style: AppType.displayItalic(colors.correction, fontSize: 18)),
          if (error.rule.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(
              error.rule,
              style: AppType.label(colors.textSecondary).copyWith(fontSize: 13),
            ),
          ],
          if (error.explanation.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(
              error.explanation,
              style: AppType.body(colors.textMuted).copyWith(fontSize: 13),
            ),
          ],
          if (error.examples.isNotEmpty)
            _LabeledLines(
              label: 'exemples',
              lines: error.examples,
              color: colors.textMuted,
            ),
          if (error.alternatives.isNotEmpty)
            _LabeledLines(
              label: 'tu peux aussi dire',
              lines: error.alternatives,
              color: colors.correction,
            ),
        ],
      ),
    );
  }
}

/// A small labeled list (an overline + one bulleted line per item), used for a
/// correction's examples and alternative phrasings.
class _LabeledLines extends StatelessWidget {
  const _LabeledLines({
    required this.label,
    required this.lines,
    required this.color,
  });

  final String label;
  final List<String> lines;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          OverlineText(label, color: color),
          const SizedBox(height: AppSpacing.xs),
          for (final line in lines)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Text(
                '· $line',
                style: AppType.body(colors.textPrimary).copyWith(fontSize: 13),
              ),
            ),
        ],
      ),
    );
  }
}

/// A cream card: surface fill, hairline border, no Material elevation.
class _Panel extends StatelessWidget {
  const _Panel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(AppRadius.hero),
        border: Border.all(color: colors.border, width: AppStroke.hairline),
      ),
      child: child,
    );
  }
}

import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../data/models/turn_correction.dart';
import '../../../design_system/atoms/overline_text.dart';

/// Opens the grammar detail sheet for a correction: the rule (the "why") and
/// alternative phrasings (the "grammar options" the learner asked for).
Future<void> showGrammarSheet(
  BuildContext context,
  TurnCorrection correction,
) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: context.colors.surface,
    showDragHandle: true,
    builder: (_) => _GrammarSheet(correction: correction),
  );
}

class _GrammarSheet extends StatelessWidget {
  const _GrammarSheet({required this.correction});

  final TurnCorrection correction;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final gold = colors.correction;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.xl,
          0,
          AppSpacing.xl,
          AppSpacing.xl,
        ),
        child: Column(
          key: const Key('grammar_sheet'),
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            OverlineText('ta correction', color: gold),
            const SizedBox(height: AppSpacing.md),
            Text.rich(
              TextSpan(
                style: AppType.displayMd(colors.textPrimary),
                children: [
                  TextSpan(
                    text: correction.original,
                    style: TextStyle(
                      color: colors.textMuted,
                      decoration: TextDecoration.lineThrough,
                    ),
                  ),
                  const TextSpan(text: '  →  '),
                  TextSpan(text: correction.correction, style: TextStyle(color: gold)),
                ],
              ),
            ),
            if (correction.rule.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.lg),
              Text(correction.rule, style: AppType.body(colors.textSecondary)),
            ],
            if (correction.alternatives.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.xl),
              OverlineText('tu peux aussi dire', color: colors.textMuted),
              const SizedBox(height: AppSpacing.sm),
              for (final alt in correction.alternatives)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.xs),
                  child: Text(
                    '· $alt',
                    style: AppType.body(colors.textPrimary),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

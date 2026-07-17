import 'package:flutter/material.dart';

import '../../../data/models/debrief.dart';

class PronunciationMap extends StatelessWidget {
  const PronunciationMap({super.key, required this.scores});

  final List<PronunciationScore> scores;

  @override
  Widget build(BuildContext context) {
    final reliableScores = scores.where((score) => score.hasReliableScore).toList();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Pronunciation map',
              key: const Key('pronunciation_map_title'),
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            if (reliableScores.isEmpty)
              const Text(
                'Not enough pronunciation data yet.',
                key: Key('pronunciation_empty'),
              )
            else
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final score in reliableScores)
                    _PronunciationChip(score: score),
                ],
              ),
            if (scores.any((score) => !score.hasReliableScore)) ...[
              const SizedBox(height: 8),
              Text(
                'Some words were skipped because the score was missing or uncertain.',
                key: const Key('pronunciation_uncertain_note'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _PronunciationChip extends StatelessWidget {
  const _PronunciationChip({required this.score});

  final PronunciationScore score;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final status = _PronunciationStatus.fromScore(score.score!);
    final label = score.phoneme == null
        ? score.word
        : '${score.word} /${score.phoneme}/';

    return Semantics(
      label:
          '$label, pronunciation ${status.label}, ${(score.score! * 100).round()} percent',
      child: Chip(
        key: Key('pronunciation_${score.word}_${score.phoneme ?? 'word'}'),
        avatar: Icon(status.icon, color: status.foreground, size: 18),
        label: Text(label),
        backgroundColor: status.background,
        labelStyle: theme.textTheme.labelLarge?.copyWith(
          color: status.foreground,
          fontWeight: FontWeight.w700,
        ),
        side: BorderSide(color: status.foreground.withValues(alpha: 0.4)),
      ),
    );
  }
}

class _PronunciationStatus {
  const _PronunciationStatus({
    required this.label,
    required this.icon,
    required this.background,
    required this.foreground,
  });

  final String label;
  final IconData icon;
  final Color background;
  final Color foreground;

  static _PronunciationStatus fromScore(double score) {
    if (score >= 0.8) {
      return const _PronunciationStatus(
        label: 'strong',
        icon: Icons.check_circle_outline,
        background: Color(0xFFE7F5EC),
        foreground: Color(0xFF176B3A),
      );
    }
    if (score >= 0.6) {
      return const _PronunciationStatus(
        label: 'review',
        icon: Icons.error_outline,
        background: Color(0xFFFFF4D6),
        foreground: Color(0xFF8A5A00),
      );
    }
    return const _PronunciationStatus(
      label: 'needs practice',
      icon: Icons.cancel_outlined,
      background: Color(0xFFFFE8E6),
      foreground: Color(0xFF9A291F),
    );
  }
}

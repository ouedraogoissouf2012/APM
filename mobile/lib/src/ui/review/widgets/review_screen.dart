import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
import '../../../data/models/review_item.dart';
import '../error_type_label.dart';
import '../view_model/review_view_model.dart';

/// « À réviser » — the recurring mistakes the spaced-repetition schedule has
/// surfaced for today. Each item shows what to work on and its most recent
/// correction; a session re-practises them (the schedule updates on the next
/// debrief, mastering a type after 3 clean sessions).
class ReviewScreen extends ConsumerWidget {
  const ReviewScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(reviewProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('À réviser')),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(
          child: Text('Impossible de charger ta révision.', key: Key('review_error')),
        ),
        data: (items) => items.isEmpty
            ? const _EmptyReview()
            : _ReviewList(items: items),
      ),
    );
  }
}

class _EmptyReview extends StatelessWidget {
  const _EmptyReview();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.check_circle_outline, size: 48),
            const SizedBox(height: 12),
            const Text(
              'Rien à réviser pour le moment 🎉',
              key: Key('review_empty'),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 4),
            Text(
              'Tes fautes récurrentes réapparaîtront ici selon un rythme espacé.',
              style: Theme.of(context).textTheme.bodySmall,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}

class _ReviewList extends ConsumerWidget {
  const _ReviewList({required this.items});

  final List<ReviewItem> items;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Column(
      children: [
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: items.length,
            separatorBuilder: (_, _) => const SizedBox(height: 12),
            itemBuilder: (_, i) => _ReviewCard(item: items[i]),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              key: const Key('review_practice_button'),
              icon: const Icon(Icons.mic),
              label: const Text('Re-pratiquer maintenant'),
              // Re-practice via a normal conversation; the schedule updates on the
              // next debrief (a type unseen for 3 sessions becomes mastered).
              onPressed: () => context.go(Routes.conversationFree),
            ),
          ),
        ),
      ],
    );
  }
}

class _ReviewCard extends StatelessWidget {
  const _ReviewCard({required this.item});

  final ReviewItem item;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      key: Key('review_card_${item.errorType}'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              errorTypeLabel(item.errorType),
              style: theme.textTheme.titleMedium,
            ),
            if (item.latestCorrection.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                'La bonne forme : « ${item.latestCorrection} »',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.tertiary,
                ),
              ),
            ],
            const SizedBox(height: 8),
            Text(
              '${item.cleanStreak} / 3 sessions sans cette faute',
              style: theme.textTheme.labelSmall,
            ),
          ],
        ),
      ),
    );
  }
}

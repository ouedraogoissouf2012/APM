import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../data/models/vocabulary_entry.dart';
import '../view_model/vocabulary_view_model.dart';

/// The vocabulary notebook (« Mot du jour »): the salient words the debrief
/// captured from the learner's own sentences, each on a WordCard with audio and
/// Encore / Je le sais actions (DESIGN_SPEC §5.6).
class VocabularyScreen extends ConsumerWidget {
  const VocabularyScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(vocabularyViewModelProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Mon carnet')),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(
          child: Text('Impossible de charger ton carnet.', key: Key('vocab_error')),
        ),
        data: (entries) {
          if (entries.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  'Ton carnet se remplira au fil des conversations : je note les '
                  'mots que tu utilises pour que tu les révises.',
                  key: Key('vocab_empty'),
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: entries.length,
            separatorBuilder: (_, _) => const SizedBox(height: 12),
            itemBuilder: (_, i) => _WordCard(entry: entries[i]),
          );
        },
      ),
    );
  }
}

class _WordCard extends ConsumerWidget {
  const _WordCard({required this.entry});

  final VocabularyEntry entry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final vm = ref.read(vocabularyViewModelProvider.notifier);
    return Card(
      key: Key('vocab_card_${entry.id}'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (entry.sessionId != null)
              Text(
                'VU EN SESSION #${entry.sessionId}',
                style: theme.textTheme.labelSmall?.copyWith(
                  letterSpacing: 1.2,
                  color: theme.colorScheme.tertiary,
                ),
              ),
            const SizedBox(height: 6),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(entry.word, style: theme.textTheme.headlineSmall),
                      if (entry.phonetic.isNotEmpty)
                        Text(
                          entry.phonetic,
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontStyle: FontStyle.italic,
                          ),
                        ),
                      if (entry.translation.isNotEmpty)
                        Text(
                          '« ${entry.translation} »',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: theme.colorScheme.tertiary,
                            fontStyle: FontStyle.italic,
                          ),
                        ),
                    ],
                  ),
                ),
                IconButton(
                  key: Key('vocab_audio_${entry.id}'),
                  icon: const Icon(Icons.volume_up),
                  tooltip: 'Écouter',
                  onPressed: () => vm.speak(entry),
                ),
              ],
            ),
            if (entry.example.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                '« ${entry.example} » — toi',
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontStyle: FontStyle.italic,
                ),
              ),
            ],
            const SizedBox(height: 12),
            Row(
              children: [
                OutlinedButton(
                  key: Key('vocab_review_${entry.id}'),
                  onPressed: () => vm.mark(entry, known: false),
                  child: const Text('Encore'),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  key: Key('vocab_known_${entry.id}'),
                  onPressed: () => vm.mark(entry, known: true),
                  child: const Text('Je le sais'),
                ),
                const Spacer(),
                if (entry.isKnown)
                  Icon(Icons.check_circle, color: theme.colorScheme.primary),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

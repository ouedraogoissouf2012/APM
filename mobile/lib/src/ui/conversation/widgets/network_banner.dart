import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/offline/connectivity_controller.dart';

/// A slim banner shown when the app is offline or has turns queued (#127). It
/// tells the learner their spoken turns are safe and offers to retry sending
/// them now. Renders nothing when online with an empty queue.
class NetworkBanner extends ConsumerWidget {
  const NetworkBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(connectivityControllerProvider);
    if (state.online && !state.hasPending) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final n = state.pendingCount;
    final label = state.online
        ? '$n phrase${n > 1 ? 's' : ''} en attente d’envoi'
        : 'Hors ligne — ${n > 0 ? '$n phrase${n > 1 ? 's' : ''} en file' : 'tes phrases seront envoyées à la reconnexion'}';

    return Material(
      color: theme.colorScheme.secondaryContainer,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        child: Row(
          key: const Key('network_banner'),
          children: [
            const Icon(Icons.cloud_off, size: 18),
            const SizedBox(width: 8),
            Expanded(child: Text(label, style: theme.textTheme.bodySmall)),
            if (state.hasPending)
              TextButton(
                key: const Key('network_retry'),
                onPressed: () => ref
                    .read(connectivityControllerProvider.notifier)
                    .syncPending(),
                child: const Text('Réessayer'),
              ),
          ],
        ),
      ),
    );
  }
}

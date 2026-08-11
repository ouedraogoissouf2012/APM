import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../ui/conversation/view_model/conversation_providers.dart';
import '../observability/providers.dart';
import 'offline_turn_queue.dart';
import 'offline_turn_sync.dart';

/// The persisted offline turn queue (secure-storage backed).
final offlineTurnQueueProvider = Provider<OfflineTurnQueue>(
  (ref) => SecureOfflineTurnQueue(SecureKeyValueStore()),
);

/// Replays queued turns (with idempotency keys) when connectivity returns.
final offlineTurnSyncProvider = Provider<OfflineTurnSync>(
  (ref) => OfflineTurnSync(
    ref.watch(offlineTurnQueueProvider),
    ref.watch(conversationRepositoryProvider),
    ref.watch(crashReporterProvider),
  ),
);

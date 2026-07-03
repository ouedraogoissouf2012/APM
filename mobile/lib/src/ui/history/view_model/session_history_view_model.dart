import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../data/models/session_summary.dart';
import '../../../data/repositories/session_history_repository.dart';
import '../../auth/view_model/auth_view_model.dart';

final sessionHistoryRepositoryProvider = Provider<SessionHistoryRepository>(
  (ref) => SessionHistoryRepository(ref.watch(authenticatedApiClientProvider)),
);

final sessionHistoryProvider = FutureProvider<List<SessionSummary>>(
  (ref) => ref.read(sessionHistoryRepositoryProvider).listRecent(),
);

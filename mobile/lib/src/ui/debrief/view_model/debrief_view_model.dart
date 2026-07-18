import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../data/models/debrief.dart';
import '../../../data/repositories/debrief_repository.dart';

final debriefRepositoryProvider = Provider<DebriefRepository>(
  (ref) => DebriefRepository(ref.watch(authenticatedApiClientProvider)),
);

/// Generates the debrief for a session once and caches it per session id.
final debriefProvider = FutureProvider.family<Debrief, int>(
  (ref, sessionId) =>
      ref.read(debriefRepositoryProvider).getOrGenerate(sessionId),
);

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../data/models/debrief.dart';
import '../../../data/repositories/debrief_repository.dart';

final debriefRepositoryProvider = Provider<DebriefRepository>(
  (ref) => DebriefRepository(ref.watch(authenticatedApiClientProvider)),
);

/// Generates the debrief for a session once and caches it per session id.
///
/// keepAlive: the result (or its error) is cached for the session, so a rebuild
/// of the debrief screen does NOT re-trigger getOrGenerate. Without it, a flicker
/// on a session that can't be debriefed hammered the endpoint (GET 404 -> POST
/// 404 -> ... on every rebuild).
final debriefProvider = FutureProvider.family<Debrief, int>(
  (ref, sessionId) {
    ref.keepAlive();
    return ref.read(debriefRepositoryProvider).getOrGenerate(sessionId);
  },
);

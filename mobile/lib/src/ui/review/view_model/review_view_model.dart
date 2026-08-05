import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../data/models/review_item.dart';
import '../../../data/repositories/review_repository.dart';

final reviewRepositoryProvider = Provider<ReviewRepository>(
  (ref) => ReviewRepository(ref.watch(authenticatedApiClientProvider)),
);

/// The error types due for spaced-repetition review right now (soonest first).
/// Auto-refreshing: invalidate this provider to re-fetch after a session.
final reviewProvider = FutureProvider<List<ReviewItem>>(
  (ref) => ref.read(reviewRepositoryProvider).dueItems(),
);

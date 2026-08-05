import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../data/models/streak.dart';
import '../../../data/repositories/streak_repository.dart';

final streakRepositoryProvider = Provider<StreakRepository>(
  (ref) => StreakRepository(ref.watch(authenticatedApiClientProvider)),
);

/// The learner's current streak + weekly progress, for the Home pill.
final streakProvider = FutureProvider<Streak>(
  (ref) => ref.read(streakRepositoryProvider).load(),
);

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../data/models/progress_snapshot.dart';
import '../../../data/repositories/progress_repository.dart';

final progressRepositoryProvider = Provider<ProgressRepository>(
  (ref) => ProgressRepository(ref.watch(authenticatedApiClientProvider)),
);

final progressProvider = FutureProvider<ProgressSnapshot>(
  (ref) => ref.read(progressRepositoryProvider).load(),
);

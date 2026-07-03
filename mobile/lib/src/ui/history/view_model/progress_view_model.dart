import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../data/models/progress_snapshot.dart';
import '../../../data/repositories/progress_repository.dart';
import '../../auth/view_model/auth_view_model.dart';

final progressRepositoryProvider = Provider<ProgressRepository>(
  (ref) => ProgressRepository(ref.watch(authenticatedApiClientProvider)),
);

final progressProvider = FutureProvider<ProgressSnapshot>(
  (ref) => ref.read(progressRepositoryProvider).load(),
);

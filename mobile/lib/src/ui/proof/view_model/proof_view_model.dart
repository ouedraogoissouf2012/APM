import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../data/models/proof.dart';
import '../../../data/repositories/proof_repository.dart';

final proofRepositoryProvider = Provider<ProofRepository>(
  (ref) => ProofRepository(ref.watch(authenticatedApiClientProvider)),
);

/// The before/after proof for a skill, or null when there isn't enough history
/// to compare yet.
final proofProvider = FutureProvider.family<Proof?, String>(
  (ref, skill) => ref.read(proofRepositoryProvider).forSkill(skill),
);

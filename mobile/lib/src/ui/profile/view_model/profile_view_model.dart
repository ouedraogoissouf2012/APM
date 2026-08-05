import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../data/models/profile.dart';
import '../../../data/repositories/profile_repository.dart';

final profileRepositoryProvider = Provider<ProfileRepository>(
  (ref) => ProfileRepository(ref.watch(authenticatedApiClientProvider)),
);

final profileViewModelProvider =
    AsyncNotifierProvider<ProfileViewModel, Profile>(ProfileViewModel.new);

/// Parses the free-text interests input ("football, cooking") into a clean list.
List<String> parseInterests(String raw) => raw
    .split(',')
    .map((s) => s.trim())
    .where((s) => s.isNotEmpty)
    .toList();

class ProfileViewModel extends AsyncNotifier<Profile> {
  @override
  Future<Profile> build() => ref.read(profileRepositoryProvider).getProfile();

  /// Saves the profile. Returns true on success; on failure the previous
  /// profile data is restored (so the form stays usable) and false is
  /// returned — the UI must NOT claim success.
  Future<bool> save({
    String? interestsText,
    String? goal,
    String? correctionIntensity,
    String? accent,
    String? memorySummary,
  }) async {
    final previous = state.value;
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref
          .read(profileRepositoryProvider)
          .updateProfile(
            interests: interestsText == null
                ? null
                : parseInterests(interestsText),
            goal: goal,
            correctionIntensity: correctionIntensity,
            accent: accent,
            memorySummary: memorySummary,
          ),
    );
    if (state.hasError) {
      if (previous != null) state = AsyncData(previous);
      return false;
    }
    return true;
  }

  /// Saves an edited memory summary (what the assistant knows about the learner).
  Future<bool> saveMemory(String memorySummary) =>
      save(memorySummary: memorySummary);

  /// Clears the memory entirely — the learner's "forget what you know about me".
  Future<bool> clearMemory() => save(memorySummary: '');
}

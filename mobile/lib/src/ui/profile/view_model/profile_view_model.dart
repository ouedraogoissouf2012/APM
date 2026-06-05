import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../data/models/profile.dart';
import '../../../data/repositories/profile_repository.dart';
import '../../auth/view_model/auth_view_model.dart';

final profileRepositoryProvider = Provider<ProfileRepository>(
  (ref) => ProfileRepository(ref.watch(apiClientProvider), ref.watch(tokenStorageProvider)),
);

final profileViewModelProvider =
    AsyncNotifierProvider<ProfileViewModel, Profile>(ProfileViewModel.new);

class ProfileViewModel extends AsyncNotifier<Profile> {
  @override
  Future<Profile> build() => ref.read(profileRepositoryProvider).getProfile();

  Future<void> save({
    List<String>? interests,
    String? goal,
    String? correctionIntensity,
    String? accent,
  }) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref.read(profileRepositoryProvider).updateProfile(
            interests: interests,
            goal: goal,
            correctionIntensity: correctionIntensity,
            accent: accent,
          ),
    );
  }
}

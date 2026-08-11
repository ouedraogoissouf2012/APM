import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/network/providers.dart';
import '../../../data/models/app_user.dart';
import '../../../data/repositories/auth_repository.dart';
import '../../profile/view_model/profile_view_model.dart';

// Plain Riverpod providers (no codegen) — fewer moving parts, simple to maintain.
// Infrastructure providers (HTTP clients, token storage) live in
// core/network/providers.dart; this file only owns the auth feature.

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(
    ref.watch(apiClientProvider),
    ref.watch(tokenStorageProvider),
  ),
);

/// Holds the current authenticated user (null = signed out). Loads on startup.
final authViewModelProvider = AsyncNotifierProvider<AuthViewModel, AppUser?>(
  AuthViewModel.new,
);

class AuthViewModel extends AsyncNotifier<AppUser?> {
  @override
  Future<AppUser?> build() => ref.watch(authRepositoryProvider).currentUser();

  Future<void> login({required String email, required String password}) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref
          .read(authRepositoryProvider)
          .login(email: email, password: password),
    );
  }

  Future<void> register({
    required String email,
    required String password,
    String nativeLanguage = AppConfig.defaultNativeLanguage,
  }) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref
          .read(authRepositoryProvider)
          .register(
            email: email,
            password: password,
            nativeLanguage: nativeLanguage,
          ),
    );
  }

  Future<void> logout() async {
    await ref.read(authRepositoryProvider).logout();
    // Drop per-user caches: without this, the next account on this device
    // would inherit the previous learner's profile (e.g. accent preference).
    ref.invalidate(profileViewModelProvider);
    // Purge the raw voice takes (#226): they must not outlive THIS user's
    // session on a shared device — the next account logging in here must not
    // be able to hear a previous learner's spoken audio. Best-effort, like the
    // capture path itself: a purge failure must never block logout.
    try {
      await ref.read(voiceTakeStoreProvider).eraseAll();
    } catch (_) {}
    state = const AsyncData(null);
  }
}

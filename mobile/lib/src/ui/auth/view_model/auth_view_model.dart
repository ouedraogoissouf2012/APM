import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/audio/user_scoped_voice_take_store.dart';
import '../../../core/config/app_config.dart';
import '../../../core/network/providers.dart';
import '../../../core/observability/providers.dart';
import '../../../core/offline/offline_turn_queue.dart';
import '../../../core/offline/providers.dart';
import '../../../data/models/app_user.dart';
import '../../../data/repositories/auth_repository.dart';

// Plain Riverpod providers (no codegen) — fewer moving parts, simple to maintain.
// Infrastructure providers (HTTP clients, token storage) live in
// core/network/providers.dart; this file only owns the auth feature.

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(
    ref.watch(apiClientProvider),
    ref.watch(tokenStorageProvider),
    ref.watch(tokenRefresherProvider),
  ),
);

/// Holds the current authenticated user (null = signed out). Loads on startup.
final authViewModelProvider = AsyncNotifierProvider<AuthViewModel, AppUser?>(
  AuthViewModel.new,
);

/// A capability that must be told which user is active — reset to `null` on
/// sign-out, re-synced whenever a new session starts. Adapts
/// [VoiceTakeUserSession]/[OfflineTurnQueueUserSession]'s existing
/// `setCurrentUser` (declared in core/audio and core/offline respectively,
/// each with an identical signature but no shared interface of their own)
/// so [AuthViewModel] can hold ONE list and iterate it (#373) instead of a
/// pair of near-identical `_sync*User` methods — each of which used to be
/// called by hand at all FOUR of build()/login()/register()/logout()'s
/// session-change points. Adding a third capability meant adding both a new
/// method AND four new call sites; forgetting one silently left that
/// capability out of sync with who's actually signed in. Adding one here
/// means editing exactly [AuthViewModel._sessionScopedCapabilities].
class UserSessionScoped {
  UserSessionScoped(this.setCurrentUser);

  final void Function(int? userId) setCurrentUser;
}

class AuthViewModel extends AsyncNotifier<AppUser?> {
  @override
  Future<AppUser?> build() async {
    final user = await ref.watch(authRepositoryProvider).currentUser();
    // Keep every per-user capability's key-scoping in sync (#319, #349) — a
    // session restored on app start (still-valid tokens, no fresh
    // login/register call) is the one transition login()/register() below
    // don't cover.
    _syncSessionScopedCapabilities(user);
    return user;
  }

  Future<void> login({required String email, required String password}) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref
          .read(authRepositoryProvider)
          .login(email: email, password: password),
    );
    _syncSessionScopedCapabilities(state.value);
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
    _syncSessionScopedCapabilities(state.value);
  }

  Future<void> logout() async {
    // Signal loading FIRST (#319): app_router.dart redirects away from any
    // protected route while authViewModelProvider.isLoading, so this closes
    // a race that would otherwise undermine the purge below — without it, a
    // learner can stay on (or navigate to) the conversation/proof screens for
    // the whole async duration of this method, and a concurrent saveTake
    // (push_to_talk_controller.dart) or takesFor read could interleave with
    // the purge: a save arriving after eraseAll() physically wiped the
    // directory recreates it (FileVoiceTakeStore._dir_), silently undoing an
    // "erased" purge, and a read while _currentUserId is still valid could
    // race the pending-purge bookkeeping below.
    state = const AsyncLoading();
    await ref.read(authRepositoryProvider).logout();
    // Every per-user CACHE provider (profile/streak/progress/review/
    // voice-consent/vocabulary/proof/debrief/mission) used to be dropped
    // right here with a hand-maintained list of 9 `ref.invalidate` calls
    // (#348) — fragile, since a 10th per-user provider added later could
    // silently be left off that list, reintroducing exactly the
    // cross-account leak #348 fixed. #373 replaces it structurally: those
    // providers are scoped into a [UserSessionScope]-owned ProviderScope
    // (main.dart), keyed on the signed-in user's id, so they're torn down
    // automatically the moment `state` below flips this id to `null` —
    // there is nothing to invalidate here, and nothing to remember to add.
    //
    // Purge the raw voice takes (#226): they must not outlive THIS user's
    // session on a shared device — the next account logging in here must not
    // be able to hear a previous learner's spoken audio. Still signed in as
    // the departing user at this point (see _syncSessionScopedCapabilities
    // below) so a FAILED purge here is tagged to THEM specifically (#319) —
    // the store then refuses to read their takes back, even if they're the
    // one who signs back in on this device.
    await _bestEffortPurge(
      () => ref.read(voiceTakeStoreProvider).eraseAll(),
      'AuthViewModel.logout: voice take purge failed',
    );
    // Purge this user's queued-but-unsent turns (#349): PendingTurn.text is
    // the learner's own spoken utterance, so it must not linger on a shared
    // device once they've signed out. Still tagged to the departing user at
    // this point (see _syncSessionScopedCapabilities below), which is what
    // makes this purge target the RIGHT key.
    await _bestEffortPurge(() async {
      final queue = ref.read(offlineTurnQueueProvider);
      if (queue is OfflineTurnQueueUserSession) {
        await (queue as OfflineTurnQueueUserSession).purgeCurrentUser();
      }
    }, 'AuthViewModel.logout: offline turn queue purge failed');
    // Now clear the session: no one is signed in until the next login. This
    // is also what UserSessionScope watches to key/dispose the per-user
    // provider subtree above.
    _syncSessionScopedCapabilities(null);
    state = const AsyncData(null);
  }

  /// Runs [purge] and reports (never rethrows) a failure. Best-effort, like
  /// the capture paths themselves: a purge failure must never block logout —
  /// but (#236) it must not vanish silently either, since it means whatever
  /// [purge] was meant to erase is still sitting on this shared device.
  Future<void> _bestEffortPurge(
    Future<void> Function() purge,
    String context,
  ) async {
    try {
      await purge();
    } catch (e, stack) {
      ref.read(crashReporterProvider).captureError(e, stack, context: context);
    }
  }

  /// Every per-user capability registered with [AuthViewModel] (#373) — see
  /// [UserSessionScoped]. A capability is a no-op inclusion unless the
  /// resolved instance actually is user-scoped (both are in production —
  /// see persistent_voice_take_store*.dart / SecureOfflineTurnQueue — a
  /// plain fake in a unit test may not be, harmlessly).
  List<UserSessionScoped> _sessionScopedCapabilities() {
    final capabilities = <UserSessionScoped>[];
    final store = ref.read(voiceTakeStoreProvider);
    if (store is VoiceTakeUserSession) {
      capabilities.add(
        UserSessionScoped((store as VoiceTakeUserSession).setCurrentUser),
      );
    }
    final queue = ref.read(offlineTurnQueueProvider);
    if (queue is OfflineTurnQueueUserSession) {
      capabilities.add(
        UserSessionScoped((queue as OfflineTurnQueueUserSession).setCurrentUser),
      );
    }
    return capabilities;
  }

  /// Keeps every per-user capability's key-scoping (#319, #349) aligned with
  /// the session by iterating [_sessionScopedCapabilities] — the single call
  /// site a new capability needs to be added to, instead of a new
  /// `_syncXUser` method duplicated at all four of this class's
  /// session-change points.
  void _syncSessionScopedCapabilities(AppUser? user) {
    for (final capability in _sessionScopedCapabilities()) {
      capability.setCurrentUser(user?.id);
    }
  }
}

import 'package:flutter_riverpod/flutter_riverpod.dart';
// ProviderOrFamily (userScopedProviders' element type, #373) is kept out of
// the main flutter_riverpod barrel and only re-exported here.
import 'package:flutter_riverpod/misc.dart';

import '../../../core/audio/providers.dart';
import '../../../core/audio/user_scoped_voice_take_store.dart';
import '../../../core/config/app_config.dart';
import '../../../core/network/providers.dart';
import '../../../core/observability/providers.dart';
import '../../../core/offline/offline_turn_queue.dart';
import '../../../core/offline/providers.dart';
import '../../../data/models/app_user.dart';
import '../../../data/repositories/auth_repository.dart';
import '../../conversation/view_model/conversation_view_model.dart';
import '../../debrief/view_model/debrief_view_model.dart';
import '../../history/view_model/progress_view_model.dart';
import '../../home/view_model/streak_view_model.dart';
import '../../missions/view_model/mission_view_model.dart';
import '../../onboarding/view_model/placement_view_model.dart';
import '../../privacy/view_model/voice_privacy_view_model.dart';
import '../../profile/view_model/profile_view_model.dart';
import '../../proof/view_model/proof_view_model.dart';
import '../../review/view_model/review_view_model.dart';
import '../../vocabulary/view_model/vocabulary_view_model.dart';

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

/// Every per-user provider that must be reset when the signed-in user
/// changes (#373 rework, after #378's nested-`ProviderScope` attempt was
/// found to leak: a ROOT-scoped provider that reads a per-user provider —
/// e.g. `effectiveServerSttProvider` watching `voiceConsentProvider` — gets
/// its own instance in the root container, which the nested scope's
/// teardown never reaches). Back to a single flat container, with
/// `ref.invalidate` for each entry — but driven by THIS list instead of a
/// hand-written sequence of calls, so a new per-user provider only needs to
/// be added HERE. `voiceTakesProvider` and `conversationViewModelProvider`
/// (#382, #388) were both silently missing from the old hand-written list;
/// that is exactly the class of omission a single registry closes.
///
/// `.family` providers (`proofProvider`, `debriefProvider`,
/// `voiceTakesProvider`) invalidate their WHOLE family — every cached id,
/// not just one — the right thing here since logout doesn't know which ids
/// were viewed.
final List<ProviderOrFamily> userScopedProviders = List.unmodifiable([
  profileViewModelProvider,
  streakProvider,
  progressProvider,
  reviewProvider,
  voiceConsentProvider,
  vocabularyViewModelProvider,
  proofProvider,
  debriefProvider,
  missionViewModelProvider,
  voiceTakesProvider,
  conversationViewModelProvider,
  // Non-autoDispose, holds the learner's transcribed placement answers +
  // computed CEFR level; reachable across accounts via the register->placement
  // redirect, so it MUST be reset on logout like every other per-user provider.
  placementViewModelProvider,
]);

class AuthViewModel extends AsyncNotifier<AppUser?> {
  @override
  Future<AppUser?> build() async {
    final user = await ref.watch(authRepositoryProvider).currentUser();
    // Keep the voice-take store's key-scoping in sync (#319) — a session
    // restored on app start (still-valid tokens, no fresh login/register
    // call) is the one transition login()/register() below don't cover.
    _syncVoiceTakeUser(user);
    // Same for the offline turn queue's key-scoping (#349).
    _syncOfflineQueueUser(user);
    return user;
  }

  Future<void> login({required String email, required String password}) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
      () => ref
          .read(authRepositoryProvider)
          .login(email: email, password: password),
    );
    _syncVoiceTakeUser(state.value);
    _syncOfflineQueueUser(state.value);
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
    _syncVoiceTakeUser(state.value);
    _syncOfflineQueueUser(state.value);
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
    // Drop every per-user cache (#348, #373): every one of these is a plain
    // (non-autoDispose) provider, so without this the next account on this
    // shared device would inherit the previous learner's cached state
    // instead of loading their own. Iterates userScopedProviders (declared
    // above) instead of a hand-written sequence of calls — debriefProvider
    // also calls ref.keepAlive() internally; invalidate() still forces a
    // rebuild on next read regardless — keepAlive only blocks disposal from
    // losing listeners, not an explicit invalidation.
    for (final provider in userScopedProviders) {
      ref.invalidate(provider);
    }
    // Purge the raw voice takes (#226): they must not outlive THIS user's
    // session on a shared device — the next account logging in here must not
    // be able to hear a previous learner's spoken audio. Still signed in as
    // the departing user at this point (see _syncVoiceTakeUser below) so a
    // FAILED purge here is tagged to THEM specifically (#319) — the store
    // then refuses to read their takes back, even if they're the one who
    // signs back in on this device.
    await _bestEffortPurge(
      () => ref.read(voiceTakeStoreProvider).eraseAll(),
      'AuthViewModel.logout: voice take purge failed',
    );
    // Purge this user's queued-but-unsent turns (#349): PendingTurn.text is
    // the learner's own spoken utterance, so it must not linger on a shared
    // device once they've signed out. Still tagged to the departing user at
    // this point (see _syncOfflineQueueUser below), which is what makes this
    // purge target the RIGHT key.
    await _bestEffortPurge(() async {
      final queue = ref.read(offlineTurnQueueProvider);
      if (queue is OfflineTurnQueueUserSession) {
        await (queue as OfflineTurnQueueUserSession).purgeCurrentUser();
      }
    }, 'AuthViewModel.logout: offline turn queue purge failed');
    // Now clear the session: no one is signed in until the next login.
    _syncVoiceTakeUser(null);
    _syncOfflineQueueUser(null);
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

  /// Keeps the voice-take store's per-user key-scoping (#319) aligned with
  /// the session. A no-op unless the resolved store happens to be
  /// user-scoped (it is in production — see persistent_voice_take_store*.
  /// dart — a plain fake in a unit test may not be, harmlessly).
  void _syncVoiceTakeUser(AppUser? user) {
    final store = ref.read(voiceTakeStoreProvider);
    if (store is VoiceTakeUserSession) {
      (store as VoiceTakeUserSession).setCurrentUser(user?.id);
    }
  }

  /// Keeps the offline turn queue's per-user key-scoping (#349, mirrors
  /// _syncVoiceTakeUser/#319) aligned with the session. A no-op unless the
  /// resolved queue happens to be user-scoped (it is in production — see
  /// SecureOfflineTurnQueue — a plain fake in a unit test may not be,
  /// harmlessly).
  void _syncOfflineQueueUser(AppUser? user) {
    final queue = ref.read(offlineTurnQueueProvider);
    if (queue is OfflineTurnQueueUserSession) {
      (queue as OfflineTurnQueueUserSession).setCurrentUser(user?.id);
    }
  }
}

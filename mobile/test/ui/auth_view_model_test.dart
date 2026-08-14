import 'dart:typed_data';

import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/core/audio/user_scoped_voice_take_store.dart';
import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:apm/src/core/network/providers.dart';
import 'package:apm/src/core/observability/crash_reporter.dart';
import 'package:apm/src/core/observability/providers.dart';
import 'package:apm/src/core/offline/offline_turn_queue.dart';
import 'package:apm/src/core/offline/pending_turn.dart';
import 'package:apm/src/core/offline/providers.dart';
import 'package:apm/src/data/models/app_user.dart';
import 'package:apm/src/data/models/debrief.dart';
import 'package:apm/src/data/models/mission.dart';
import 'package:apm/src/data/models/progress_snapshot.dart';
import 'package:apm/src/data/models/review_item.dart';
import 'package:apm/src/data/models/streak.dart';
import 'package:apm/src/data/models/vocabulary_entry.dart';
import 'package:apm/src/data/models/voice_consent.dart';
import 'package:apm/src/data/repositories/auth_repository.dart';
import 'package:apm/src/data/repositories/debrief_repository.dart';
import 'package:apm/src/data/repositories/progress_repository.dart';
import 'package:apm/src/data/repositories/proof_repository.dart';
import 'package:apm/src/data/repositories/review_repository.dart';
import 'package:apm/src/data/repositories/runtime_config_repository.dart';
import 'package:apm/src/data/repositories/streak_repository.dart';
import 'package:apm/src/data/repositories/vocabulary_repository.dart';
import 'package:apm/src/data/repositories/voice_privacy_repository.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_state.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_view_model.dart';
import 'package:apm/src/ui/debrief/view_model/debrief_view_model.dart';
import 'package:apm/src/ui/history/view_model/progress_view_model.dart';
import 'package:apm/src/ui/home/view_model/streak_view_model.dart';
import 'package:apm/src/ui/missions/view_model/mission_view_model.dart';
import 'package:apm/src/ui/privacy/view_model/voice_privacy_view_model.dart';
import 'package:apm/src/ui/proof/view_model/proof_view_model.dart';
import 'package:apm/src/ui/review/view_model/review_view_model.dart';
import 'package:apm/src/ui/vocabulary/view_model/vocabulary_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuthRepository extends Mock implements AuthRepository {}

class _MockCrashReporter extends Mock implements CrashReporter {}

class _MockStreakRepository extends Mock implements StreakRepository {}

class _MockProgressRepository extends Mock implements ProgressRepository {}

class _MockReviewRepository extends Mock implements ReviewRepository {}

class _MockVoicePrivacyRepository extends Mock
    implements VoicePrivacyRepository {}

class _MockVocabularyRepository extends Mock implements VocabularyRepository {}

class _MockProofRepository extends Mock implements ProofRepository {}

class _MockDebriefRepository extends Mock implements DebriefRepository {}

/// Records every setCurrentUser()/purgeCurrentUser() call (#349), mirroring
/// _SpyVoiceTakeStore, so a test can assert the logout->purge wiring and the
/// session-sync wiring without touching a real secure-storage-backed queue.
class _SpyOfflineTurnQueue
    implements OfflineTurnQueue, OfflineTurnQueueUserSession {
  int purgeCalls = 0;
  Object? throwOnPurge;
  final List<int?> setCurrentUserCalls = [];

  @override
  void setCurrentUser(int? userId) => setCurrentUserCalls.add(userId);

  @override
  Future<void> purgeCurrentUser() async {
    purgeCalls++;
    final err = throwOnPurge;
    if (err != null) throw err;
  }

  @override
  Future<void> enqueue(PendingTurn turn) async {}

  @override
  Future<List<PendingTurn>> pending() async => const [];

  @override
  Future<void> remove(String idempotencyKey) async {}
}

/// Records whether/how many times eraseAll() ran, and every
/// setCurrentUser() call (#319), so a test can assert the logout->purge
/// wiring (#226) AND the session-sync wiring without touching a real
/// file/IndexedDB store.
class _SpyVoiceTakeStore implements VoiceTakeStore, VoiceTakeUserSession {
  int eraseAllCalls = 0;
  int takesForCalls = 0;
  Object? throwOnErase;
  final List<int?> setCurrentUserCalls = [];

  @override
  Future<void> saveTake(String skill, Uint8List bytes) async {}

  @override
  Future<VoiceTakes?> takesFor(String skill) async {
    takesForCalls++;
    return null;
  }

  @override
  Future<void> eraseAll() async {
    eraseAllCalls++;
    final err = throwOnErase;
    if (err != null) throw err;
  }

  @override
  Future<void> deleteSkill(String skill) async {}

  @override
  void setCurrentUser(int? userId) => setCurrentUserCalls.add(userId);
}

const _user = AppUser(
  id: 1,
  email: 'a@b.com',
  nativeLanguage: 'fr',
  cefrLevel: 'A1',
  tier: 'free',
);

ProviderContainer _containerWith(
  AuthRepository repo, {
  VoiceTakeStore? takeStore,
  CrashReporter? crashReporter,
  OfflineTurnQueue? offlineQueue,
  StreakRepository? streakRepo,
  ProgressRepository? progressRepo,
  ReviewRepository? reviewRepo,
  VoicePrivacyRepository? voicePrivacyRepo,
  VocabularyRepository? vocabularyRepo,
  ProofRepository? proofRepo,
  DebriefRepository? debriefRepo,
}) {
  final c = ProviderContainer(
    overrides: [
      authRepositoryProvider.overrideWithValue(repo),
      if (takeStore != null)
        voiceTakeStoreProvider.overrideWithValue(takeStore),
      if (crashReporter != null)
        crashReporterProvider.overrideWithValue(crashReporter),
      if (offlineQueue != null)
        offlineTurnQueueProvider.overrideWithValue(offlineQueue),
      if (streakRepo != null)
        streakRepositoryProvider.overrideWithValue(streakRepo),
      if (progressRepo != null)
        progressRepositoryProvider.overrideWithValue(progressRepo),
      if (reviewRepo != null)
        reviewRepositoryProvider.overrideWithValue(reviewRepo),
      if (voicePrivacyRepo != null)
        voicePrivacyRepositoryProvider.overrideWithValue(voicePrivacyRepo),
      if (vocabularyRepo != null)
        vocabularyRepositoryProvider.overrideWithValue(vocabularyRepo),
      if (proofRepo != null)
        proofRepositoryProvider.overrideWithValue(proofRepo),
      if (debriefRepo != null)
        debriefRepositoryProvider.overrideWithValue(debriefRepo),
    ],
  );
  addTearDown(c.dispose);
  return c;
}

void main() {
  setUpAll(() => registerFallbackValue(StackTrace.empty));

  test('build returns null when signed out', () async {
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => null);
    final c = _containerWith(repo);

    final user = await c.read(authViewModelProvider.future);
    expect(user, isNull);
  });

  test('login sets the authenticated user', () async {
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => null);
    when(
      () => repo.login(
        email: any(named: 'email'),
        password: any(named: 'password'),
      ),
    ).thenAnswer((_) async => _user);
    final c = _containerWith(repo);

    await c.read(authViewModelProvider.future); // initial build
    await c
        .read(authViewModelProvider.notifier)
        .login(email: 'a@b.com', password: 's3cret!');

    expect(c.read(authViewModelProvider).value, _user);
  });

  test('logout clears the user', () async {
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => _user);
    when(repo.logout).thenAnswer((_) async {});
    final c = _containerWith(repo);

    await c.read(authViewModelProvider.future);
    await c.read(authViewModelProvider.notifier).logout();

    expect(c.read(authViewModelProvider).value, isNull);
  });

  test('logout purges the on-device voice takes (#226)', () async {
    // A shared device: the NEXT account logging in here must not be able to
    // hear this learner's spoken audio.
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => _user);
    when(repo.logout).thenAnswer((_) async {});
    final takeStore = _SpyVoiceTakeStore();
    final c = _containerWith(repo, takeStore: takeStore);

    await c.read(authViewModelProvider.future);
    await c.read(authViewModelProvider.notifier).logout();

    expect(takeStore.eraseAllCalls, 1);
  });

  test('logout still succeeds even if purging voice takes fails', () async {
    // Best-effort, like the capture path itself: a purge failure must never
    // strand the learner unable to log out.
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => _user);
    when(repo.logout).thenAnswer((_) async {});
    final takeStore = _SpyVoiceTakeStore()
      ..throwOnErase = StateError('disk error');
    final c = _containerWith(repo, takeStore: takeStore);

    await c.read(authViewModelProvider.future);
    await c.read(authViewModelProvider.notifier).logout();

    expect(
      c.read(authViewModelProvider).value,
      isNull,
    ); // logout still completed
    expect(takeStore.eraseAllCalls, 1); // the purge was attempted
  });

  test('a voice take purge failure at logout is reported, not silently '
      'swallowed (#236)', () async {
    // A silent failure here would mean the previous learner's audio is still
    // sitting on this shared device with no trace that the purge ever failed.
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => _user);
    when(repo.logout).thenAnswer((_) async {});
    final takeStore = _SpyVoiceTakeStore()
      ..throwOnErase = StateError('disk error');
    final reporter = _MockCrashReporter();
    final c = _containerWith(
      repo,
      takeStore: takeStore,
      crashReporter: reporter,
      // A working fake so only the voice-take purge failure is under test —
      // without this, the default (real, secure-storage-backed) offline
      // queue would ALSO fail in this unit-test environment and add its own
      // (legitimate, but irrelevant here) captureError call.
      offlineQueue: _SpyOfflineTurnQueue(),
    );

    await c.read(authViewModelProvider.future);
    await c.read(authViewModelProvider.notifier).logout();

    verify(
      () => reporter.captureError(any(), any(), context: any(named: 'context')),
    ).called(1);
  });

  group('voice-take store session sync (#319)', () {
    test('build() syncs a restored session to the store', () async {
      final repo = _MockAuthRepository();
      when(repo.currentUser).thenAnswer((_) async => _user);
      final takeStore = _SpyVoiceTakeStore();
      final c = _containerWith(repo, takeStore: takeStore);

      await c.read(authViewModelProvider.future);

      expect(takeStore.setCurrentUserCalls, [_user.id]);
    });

    test('build() syncs null when signed out', () async {
      final repo = _MockAuthRepository();
      when(repo.currentUser).thenAnswer((_) async => null);
      final takeStore = _SpyVoiceTakeStore();
      final c = _containerWith(repo, takeStore: takeStore);

      await c.read(authViewModelProvider.future);

      expect(takeStore.setCurrentUserCalls, [null]);
    });

    test('login() syncs the newly authenticated user', () async {
      final repo = _MockAuthRepository();
      when(repo.currentUser).thenAnswer((_) async => null);
      when(
        () => repo.login(
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      ).thenAnswer((_) async => _user);
      final takeStore = _SpyVoiceTakeStore();
      final c = _containerWith(repo, takeStore: takeStore);

      await c.read(authViewModelProvider.future); // build() -> signed out
      await c
          .read(authViewModelProvider.notifier)
          .login(email: 'a@b.com', password: 's3cret!');

      expect(takeStore.setCurrentUserCalls, [null, _user.id]);
    });

    test('logout() syncs back to null AFTER attempting the purge under the '
        'departing user\'s identity — a failed purge must still be tagged '
        'to THEM, not to no-one', () async {
      final repo = _MockAuthRepository();
      when(repo.currentUser).thenAnswer((_) async => _user);
      when(repo.logout).thenAnswer((_) async {});
      final takeStore = _SpyVoiceTakeStore();
      final c = _containerWith(repo, takeStore: takeStore);

      await c.read(authViewModelProvider.future); // build() -> _user.id
      await c.read(authViewModelProvider.notifier).logout();

      expect(takeStore.setCurrentUserCalls, [_user.id, null]);
    });

    test(
      'logout() syncs back to null even when the purge itself failed',
      () async {
        final repo = _MockAuthRepository();
        when(repo.currentUser).thenAnswer((_) async => _user);
        when(repo.logout).thenAnswer((_) async {});
        final takeStore = _SpyVoiceTakeStore()
          ..throwOnErase = StateError('disk error');
        final c = _containerWith(repo, takeStore: takeStore);

        await c.read(authViewModelProvider.future);
        await c.read(authViewModelProvider.notifier).logout();

        expect(takeStore.setCurrentUserCalls, [_user.id, null]);
      },
    );
  });

  group('per-user provider invalidation on logout (#348)', () {
    test(
      'every cached per-user provider is invalidated — the next account '
      'on this device never sees a previous learner\'s cached data',
      () async {
        final repo = _MockAuthRepository();
        when(repo.currentUser).thenAnswer((_) async => _user);
        when(repo.logout).thenAnswer((_) async {});

        final streakRepo = _MockStreakRepository();
        var streakCalls = 0;
        when(streakRepo.load).thenAnswer((_) async {
          streakCalls++;
          return const Streak(
            currentStreak: 0,
            longestStreak: 0,
            weeklyGoalMinutes: 0,
            minutesThisWeek: 0,
          );
        });

        final progressRepo = _MockProgressRepository();
        var progressCalls = 0;
        when(progressRepo.load).thenAnswer((_) async {
          progressCalls++;
          return const ProgressSnapshot(
            sessions: [],
            cefrTrend: [],
            recurringErrors: [],
          );
        });

        final reviewRepo = _MockReviewRepository();
        var reviewCalls = 0;
        when(reviewRepo.dueItems).thenAnswer((_) async {
          reviewCalls++;
          return <ReviewItem>[];
        });

        final voicePrivacyRepo = _MockVoicePrivacyRepository();
        var voiceConsentCalls = 0;
        when(voicePrivacyRepo.getConsent).thenAnswer((_) async {
          voiceConsentCalls++;
          return const VoiceConsent(
            transcription: true,
            scoring: false,
            b2bShare: false,
            modelTraining: false,
          );
        });

        final vocabularyRepo = _MockVocabularyRepository();
        var vocabularyCalls = 0;
        when(vocabularyRepo.list).thenAnswer((_) async {
          vocabularyCalls++;
          return <VocabularyEntry>[];
        });

        final proofRepo = _MockProofRepository();
        var proofCalls = 0;
        when(() => proofRepo.forSkill(any())).thenAnswer((_) async {
          proofCalls++;
          return null;
        });

        final debriefRepo = _MockDebriefRepository();
        var debriefCalls = 0;
        when(() => debriefRepo.getOrGenerate(any())).thenAnswer((_) async {
          debriefCalls++;
          return const Debrief(cefrEstimate: 'A1', summary: '', errors: []);
        });

        final c = _containerWith(
          repo,
          streakRepo: streakRepo,
          progressRepo: progressRepo,
          reviewRepo: reviewRepo,
          voicePrivacyRepo: voicePrivacyRepo,
          vocabularyRepo: vocabularyRepo,
          proofRepo: proofRepo,
          debriefRepo: debriefRepo,
        );

        await c.read(authViewModelProvider.future); // build() -> signed in

        // Prime every provider once, as if the FIRST account had used the app.
        await c.read(streakProvider.future);
        await c.read(progressProvider.future);
        await c.read(reviewProvider.future);
        await c.read(voiceConsentProvider.future);
        await c.read(vocabularyViewModelProvider.future);
        await c.read(proofProvider('reading').future);
        await c.read(debriefProvider(1).future);
        c
            .read(missionViewModelProvider.notifier)
            .selectSourceType(MissionSourceType.cv);

        await c.read(authViewModelProvider.notifier).logout();

        // Re-reading now must hit the repository again — not serve the
        // first account's cached value to whoever logs in next.
        await c.read(streakProvider.future);
        await c.read(progressProvider.future);
        await c.read(reviewProvider.future);
        await c.read(voiceConsentProvider.future);
        await c.read(vocabularyViewModelProvider.future);
        await c.read(proofProvider('reading').future);
        await c.read(
          debriefProvider(1).future,
        ); // keepAlive() must not block this

        expect(streakCalls, 2, reason: 'streakProvider not invalidated');
        expect(progressCalls, 2, reason: 'progressProvider not invalidated');
        expect(reviewCalls, 2, reason: 'reviewProvider not invalidated');
        expect(
          voiceConsentCalls,
          2,
          reason: 'voiceConsentProvider not invalidated',
        );
        expect(
          vocabularyCalls,
          2,
          reason: 'vocabularyViewModelProvider not invalidated',
        );
        expect(proofCalls, 2, reason: 'proofProvider not invalidated');
        expect(debriefCalls, 2, reason: 'debriefProvider not invalidated');
        expect(
          c.read(missionViewModelProvider).sourceType,
          MissionSourceType.offer, // back to the default: build() reran
          reason: 'missionViewModelProvider not invalidated',
        );
      },
    );

    test(
      'the cached decrypted voice takes are invalidated too (#382) — the '
      'next account cannot replay a previous learner\'s "Ma preuve" audio',
      () async {
        final repo = _MockAuthRepository();
        when(repo.currentUser).thenAnswer((_) async => _user);
        when(repo.logout).thenAnswer((_) async {});
        final takeStore = _SpyVoiceTakeStore();
        final c = _containerWith(repo, takeStore: takeStore);

        await c.read(authViewModelProvider.future);
        await c.read(voiceTakesProvider('reading').future);
        expect(takeStore.takesForCalls, 1);

        await c.read(authViewModelProvider.notifier).logout();

        await c.read(voiceTakesProvider('reading').future);
        expect(
          takeStore.takesForCalls,
          2,
          reason: 'voiceTakesProvider was left off the old hand-written '
              'invalidate list — a stale decrypted-audio cache would '
              'otherwise survive logout',
        );
      },
    );

    test(
      'the conversation transcript is reset too (#388) — the next account '
      'does not briefly see a previous learner\'s turns',
      () async {
        final repo = _MockAuthRepository();
        when(repo.currentUser).thenAnswer((_) async => _user);
        when(repo.logout).thenAnswer((_) async {});
        final c = _containerWith(repo);

        await c.read(authViewModelProvider.future);
        // Seed a transcript, as if the departing account had a conversation
        // going (cancel() on leaving the screen keeps sessionId+turns, so
        // this state can genuinely still be live at logout time).
        c.read(conversationViewModelProvider.notifier).state =
            const ConversationState(
              sessionId: 7,
              turns: [ConversationTurn(kRoleUser, 'my private story')],
            );
        expect(c.read(conversationViewModelProvider).turns, isNotEmpty);

        await c.read(authViewModelProvider.notifier).logout();

        expect(
          c.read(conversationViewModelProvider),
          const ConversationState(),
          reason: 'conversationViewModelProvider was left off the old '
              'hand-written invalidate list — build() must rerun to the '
              'default empty state',
        );
      },
    );

    test(
      'anti-regression (#373): a ROOT provider that reads a per-user '
      'provider is reset too — effectiveServerSttProvider (core/network, '
      'root-scoped) watches voiceConsentProvider (per-user). This is the '
      'exact scenario #378\'s nested-ProviderScope attempt got wrong: that '
      'design gave a root reader like this one its OWN copy of the '
      'per-user provider, which the nested scope\'s teardown never reached '
      '— so it kept serving the departing account\'s consent forever. A '
      'flat container + ref.invalidate does not have that problem: '
      'invalidating voiceConsentProvider here also invalidates anything '
      'that watched it, in the SAME container.',
      () async {
        final repo = _MockAuthRepository();
        when(repo.currentUser).thenAnswer((_) async => _user);
        when(repo.logout).thenAnswer((_) async {});

        var consentCalls = 0;
        final c = ProviderContainer(
          overrides: [
            authRepositoryProvider.overrideWithValue(repo),
            // Server STT is available; only consent should gate it, so a
            // stale consent value is the only way this could stay wrong.
            runtimeConfigProvider.overrideWith(
              (ref) async => const RuntimeConfig(
                demoMode: false,
                serverTts: false,
                serverStt: true,
              ),
            ),
            // A REAL provider (not overrideWithValue) so effectiveServerSttProvider
            // genuinely re-invokes it on invalidate, rather than reusing a
            // fixed value regardless of invalidation.
            voiceConsentProvider.overrideWith((ref) async {
              consentCalls++;
              return VoiceConsent(
                transcription: consentCalls == 1, // account A: granted
                scoring: false,
                b2bShare: false,
                modelTraining: false,
              );
            }),
          ],
        );
        addTearDown(c.dispose);

        await c.read(authViewModelProvider.future);

        expect(await c.read(effectiveServerSttProvider.future), isTrue);
        expect(consentCalls, 1);

        await c.read(authViewModelProvider.notifier).logout();

        expect(
          await c.read(effectiveServerSttProvider.future),
          isFalse,
          reason: 'a stale ROOT copy of voiceConsentProvider (the #378 '
              'bug) would keep returning the departing account\'s granted '
              'consent forever, regardless of logout',
        );
        expect(consentCalls, 2);
      },
    );
  });

  group('offline turn queue session sync (#349)', () {
    test(
      'logout purges the offline turn queue for the departing user',
      () async {
        final repo = _MockAuthRepository();
        when(repo.currentUser).thenAnswer((_) async => _user);
        when(repo.logout).thenAnswer((_) async {});
        final queue = _SpyOfflineTurnQueue();
        final c = _containerWith(repo, offlineQueue: queue);

        await c.read(authViewModelProvider.future);
        await c.read(authViewModelProvider.notifier).logout();

        expect(queue.purgeCalls, 1);
      },
    );

    test(
      'logout still succeeds even if purging the offline queue fails',
      () async {
        final repo = _MockAuthRepository();
        when(repo.currentUser).thenAnswer((_) async => _user);
        when(repo.logout).thenAnswer((_) async {});
        final queue = _SpyOfflineTurnQueue()
          ..throwOnPurge = StateError('disk error');
        final c = _containerWith(repo, offlineQueue: queue);

        await c.read(authViewModelProvider.future);
        await c.read(authViewModelProvider.notifier).logout();

        expect(c.read(authViewModelProvider).value, isNull);
        expect(queue.purgeCalls, 1); // the purge was attempted
      },
    );

    test('an offline-queue purge failure at logout is reported, not silently '
        'swallowed (#236)', () async {
      final repo = _MockAuthRepository();
      when(repo.currentUser).thenAnswer((_) async => _user);
      when(repo.logout).thenAnswer((_) async {});
      final queue = _SpyOfflineTurnQueue()
        ..throwOnPurge = StateError('disk error');
      final reporter = _MockCrashReporter();
      final c = _containerWith(
        repo,
        offlineQueue: queue,
        crashReporter: reporter,
        // A working fake so only the offline-queue purge failure is under
        // test — without this, the default (real, secure-storage-backed)
        // voice-take store would ALSO fail in this unit-test environment
        // and add its own (legitimate, but irrelevant here) captureError
        // call.
        takeStore: _SpyVoiceTakeStore(),
      );

      await c.read(authViewModelProvider.future);
      await c.read(authViewModelProvider.notifier).logout();

      verify(
        () =>
            reporter.captureError(any(), any(), context: any(named: 'context')),
      ).called(1);
    });

    test('build() syncs a restored session to the queue', () async {
      final repo = _MockAuthRepository();
      when(repo.currentUser).thenAnswer((_) async => _user);
      final queue = _SpyOfflineTurnQueue();
      final c = _containerWith(repo, offlineQueue: queue);

      await c.read(authViewModelProvider.future);

      expect(queue.setCurrentUserCalls, [_user.id]);
    });

    test('login() syncs the newly authenticated user', () async {
      final repo = _MockAuthRepository();
      when(repo.currentUser).thenAnswer((_) async => null);
      when(
        () => repo.login(
          email: any(named: 'email'),
          password: any(named: 'password'),
        ),
      ).thenAnswer((_) async => _user);
      final queue = _SpyOfflineTurnQueue();
      final c = _containerWith(repo, offlineQueue: queue);

      await c.read(authViewModelProvider.future); // build() -> signed out
      await c
          .read(authViewModelProvider.notifier)
          .login(email: 'a@b.com', password: 's3cret!');

      expect(queue.setCurrentUserCalls, [null, _user.id]);
    });

    test('logout() syncs back to null AFTER attempting the purge under the '
        'departing user\'s identity', () async {
      final repo = _MockAuthRepository();
      when(repo.currentUser).thenAnswer((_) async => _user);
      when(repo.logout).thenAnswer((_) async {});
      final queue = _SpyOfflineTurnQueue();
      final c = _containerWith(repo, offlineQueue: queue);

      await c.read(authViewModelProvider.future); // build() -> _user.id
      await c.read(authViewModelProvider.notifier).logout();

      expect(queue.setCurrentUserCalls, [_user.id, null]);
    });

    test(
      'logout() syncs back to null even when the purge itself failed',
      () async {
        final repo = _MockAuthRepository();
        when(repo.currentUser).thenAnswer((_) async => _user);
        when(repo.logout).thenAnswer((_) async {});
        final queue = _SpyOfflineTurnQueue()
          ..throwOnPurge = StateError('disk error');
        final c = _containerWith(repo, offlineQueue: queue);

        await c.read(authViewModelProvider.future);
        await c.read(authViewModelProvider.notifier).logout();

        expect(queue.setCurrentUserCalls, [_user.id, null]);
      },
    );
  });
}

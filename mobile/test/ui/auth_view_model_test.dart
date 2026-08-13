import 'dart:typed_data';

import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/core/audio/user_scoped_voice_take_store.dart';
import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:apm/src/core/observability/crash_reporter.dart';
import 'package:apm/src/core/observability/providers.dart';
import 'package:apm/src/core/offline/offline_turn_queue.dart';
import 'package:apm/src/core/offline/pending_turn.dart';
import 'package:apm/src/core/offline/providers.dart';
import 'package:apm/src/data/models/app_user.dart';
import 'package:apm/src/data/repositories/auth_repository.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuthRepository extends Mock implements AuthRepository {}

class _MockCrashReporter extends Mock implements CrashReporter {}

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
  Object? throwOnErase;
  final List<int?> setCurrentUserCalls = [];

  @override
  Future<void> saveTake(String skill, Uint8List bytes) async {}

  @override
  Future<VoiceTakes?> takesFor(String skill) async => null;

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

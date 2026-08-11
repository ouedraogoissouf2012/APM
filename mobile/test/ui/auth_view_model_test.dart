import 'dart:typed_data';

import 'package:apm/src/core/audio/providers.dart';
import 'package:apm/src/core/audio/voice_take_store.dart';
import 'package:apm/src/core/observability/crash_reporter.dart';
import 'package:apm/src/core/observability/providers.dart';
import 'package:apm/src/data/models/app_user.dart';
import 'package:apm/src/data/repositories/auth_repository.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuthRepository extends Mock implements AuthRepository {}

class _MockCrashReporter extends Mock implements CrashReporter {}

/// Records whether/how many times eraseAll() ran, so a test can assert the
/// logout->purge wiring (#226) without touching a real file/IndexedDB store.
class _SpyVoiceTakeStore implements VoiceTakeStore {
  int eraseAllCalls = 0;
  Object? throwOnErase;

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
}) {
  final c = ProviderContainer(
    overrides: [
      authRepositoryProvider.overrideWithValue(repo),
      if (takeStore != null) voiceTakeStoreProvider.overrideWithValue(takeStore),
      if (crashReporter != null) crashReporterProvider.overrideWithValue(crashReporter),
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
    final takeStore = _SpyVoiceTakeStore()..throwOnErase = StateError('disk error');
    final c = _containerWith(repo, takeStore: takeStore);

    await c.read(authViewModelProvider.future);
    await c.read(authViewModelProvider.notifier).logout();

    expect(c.read(authViewModelProvider).value, isNull); // logout still completed
    expect(takeStore.eraseAllCalls, 1); // the purge was attempted
  });

  test('a voice take purge failure at logout is reported, not silently '
      'swallowed (#236)', () async {
    // A silent failure here would mean the previous learner's audio is still
    // sitting on this shared device with no trace that the purge ever failed.
    final repo = _MockAuthRepository();
    when(repo.currentUser).thenAnswer((_) async => _user);
    when(repo.logout).thenAnswer((_) async {});
    final takeStore = _SpyVoiceTakeStore()..throwOnErase = StateError('disk error');
    final reporter = _MockCrashReporter();
    final c = _containerWith(repo, takeStore: takeStore, crashReporter: reporter);

    await c.read(authViewModelProvider.future);
    await c.read(authViewModelProvider.notifier).logout();

    verify(
      () => reporter.captureError(any(), any(), context: any(named: 'context')),
    ).called(1);
  });
}

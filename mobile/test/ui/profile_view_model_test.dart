import 'dart:async';

import 'package:apm/src/data/models/profile.dart';
import 'package:apm/src/data/repositories/profile_repository.dart';
import 'package:apm/src/ui/profile/view_model/profile_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockProfileRepository extends Mock implements ProfileRepository {}

const _profile = Profile(
  interests: ['football'],
  goal: 'job',
  correctionIntensity: 'gentle',
  accent: 'us',
);

ProviderContainer _containerWith(ProfileRepository repo) {
  final c = ProviderContainer(
    overrides: [profileRepositoryProvider.overrideWithValue(repo)],
  );
  addTearDown(c.dispose);
  return c;
}

void main() {
  test('build loads the current profile', () async {
    final repo = _MockProfileRepository();
    when(repo.getProfile).thenAnswer((_) async => _profile);
    final c = _containerWith(repo);

    final profile = await c.read(profileViewModelProvider.future);

    expect(profile.accent, 'us');
    expect(profile.interests, ['football']);
  });

  test('save updates the profile via the repository', () async {
    final repo = _MockProfileRepository();
    when(repo.getProfile).thenAnswer((_) async => _profile);
    when(
      () => repo.updateProfile(
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
        correctionIntensity: any(named: 'correctionIntensity'),
        accent: any(named: 'accent'),
        memorySummary: any(named: 'memorySummary'),
      ),
    ).thenAnswer(
      (_) async => const Profile(
        interests: ['cooking'],
        goal: 'travel',
        correctionIntensity: 'detailed',
        accent: 'uk',
      ),
    );
    final c = _containerWith(repo);

    await c.read(profileViewModelProvider.future);
    final saved = await c
        .read(profileViewModelProvider.notifier)
        .save(interestsText: 'cooking', accent: 'uk');

    expect(saved, isTrue);
    expect(c.read(profileViewModelProvider).value!.accent, 'uk');
    expect(c.read(profileViewModelProvider).value!.interests, ['cooking']);
  });

  test('save reports failure and restores the previous profile', () async {
    final repo = _MockProfileRepository();
    when(repo.getProfile).thenAnswer((_) async => _profile);
    when(
      () => repo.updateProfile(
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
        correctionIntensity: any(named: 'correctionIntensity'),
        accent: any(named: 'accent'),
        memorySummary: any(named: 'memorySummary'),
      ),
    ).thenThrow(Exception('network down'));
    final c = _containerWith(repo);

    await c.read(profileViewModelProvider.future);
    final saved = await c
        .read(profileViewModelProvider.notifier)
        .save(interestsText: 'cooking', accent: 'uk');

    // No false success, and the form data is still usable (previous profile).
    expect(saved, isFalse);
    expect(c.read(profileViewModelProvider).value!.accent, 'us');
  });

  test(
    'save does not flash the screen to a full-screen loading state (#335)',
    () async {
      final repo = _MockProfileRepository();
      when(repo.getProfile).thenAnswer((_) async => _profile);
      final updateCompleter = Completer<Profile>();
      when(
        () => repo.updateProfile(
          interests: any(named: 'interests'),
          goal: any(named: 'goal'),
          correctionIntensity: any(named: 'correctionIntensity'),
          accent: any(named: 'accent'),
          memorySummary: any(named: 'memorySummary'),
        ),
      ).thenAnswer((_) => updateCompleter.future);
      final c = _containerWith(repo);

      await c.read(profileViewModelProvider.future);
      final saveFuture = c
          .read(profileViewModelProvider.notifier)
          .save(interestsText: 'cooking', accent: 'uk');

      // Let save() run up to its await on the repository call, without
      // resolving it — this is the window the OLD code spent in
      // AsyncLoading(), flashing the screen to a full-screen spinner for
      // what is really a small in-place edit (the caller's local `_saving`
      // flag already drives the busy button state).
      await Future<void>.delayed(Duration.zero);
      final duringSave = c.read(profileViewModelProvider);
      expect(duringSave, isA<AsyncData<Profile>>());
      expect(duringSave.value!.accent, 'us'); // still the pre-save profile

      updateCompleter.complete(
        const Profile(
          interests: ['cooking'],
          goal: 'travel',
          correctionIntensity: 'detailed',
          accent: 'uk',
        ),
      );
      final saved = await saveFuture;

      expect(saved, isTrue);
      expect(c.read(profileViewModelProvider).value!.accent, 'uk');
    },
  );

  test('saveMemory sends the edited memory summary and updates state', () async {
    final repo = _MockProfileRepository();
    when(repo.getProfile).thenAnswer((_) async => _profile);
    when(
      () => repo.updateProfile(
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
        correctionIntensity: any(named: 'correctionIntensity'),
        accent: any(named: 'accent'),
        memorySummary: any(named: 'memorySummary'),
      ),
    ).thenAnswer(
      (_) async => const Profile(
        interests: ['football'],
        goal: 'job',
        correctionIntensity: 'gentle',
        accent: 'us',
        memorySummary: 'Loves hiking.',
      ),
    );
    final c = _containerWith(repo);

    await c.read(profileViewModelProvider.future);
    final ok = await c
        .read(profileViewModelProvider.notifier)
        .saveMemory('Loves hiking.');

    expect(ok, isTrue);
    expect(c.read(profileViewModelProvider).value!.memorySummary, 'Loves hiking.');
    verify(
      () => repo.updateProfile(memorySummary: 'Loves hiking.'),
    ).called(1);
  });

  test('clearMemory sends an empty string (forget everything)', () async {
    final repo = _MockProfileRepository();
    when(repo.getProfile).thenAnswer(
      (_) async => const Profile(
        interests: ['football'],
        goal: 'job',
        correctionIntensity: 'gentle',
        accent: 'us',
        memorySummary: 'Loves hiking.',
      ),
    );
    when(
      () => repo.updateProfile(
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
        correctionIntensity: any(named: 'correctionIntensity'),
        accent: any(named: 'accent'),
        memorySummary: any(named: 'memorySummary'),
      ),
    ).thenAnswer((_) async => _profile); // _profile has empty memory
    final c = _containerWith(repo);

    await c.read(profileViewModelProvider.future);
    final ok = await c.read(profileViewModelProvider.notifier).clearMemory();

    expect(ok, isTrue);
    expect(c.read(profileViewModelProvider).value!.memorySummary, '');
    verify(() => repo.updateProfile(memorySummary: '')).called(1);
  });

  test('parseInterests splits, trims and drops empties', () {
    expect(parseInterests(' football,  cooking , ,travel '), [
      'football',
      'cooking',
      'travel',
    ]);
    expect(parseInterests(''), isEmpty);
  });
}

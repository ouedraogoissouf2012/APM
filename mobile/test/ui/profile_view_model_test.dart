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

  test('parseInterests splits, trims and drops empties', () {
    expect(parseInterests(' football,  cooking , ,travel '), [
      'football',
      'cooking',
      'travel',
    ]);
    expect(parseInterests(''), isEmpty);
  });
}

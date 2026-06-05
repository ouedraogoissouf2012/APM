import 'package:apm/src/data/models/app_user.dart';
import 'package:apm/src/data/repositories/auth_repository.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockAuthRepository extends Mock implements AuthRepository {}

const _user = AppUser(
  id: 1,
  email: 'a@b.com',
  nativeLanguage: 'fr',
  cefrLevel: 'A1',
  tier: 'free',
);

ProviderContainer _containerWith(AuthRepository repo) {
  final c = ProviderContainer(
    overrides: [authRepositoryProvider.overrideWithValue(repo)],
  );
  addTearDown(c.dispose);
  return c;
}

void main() {
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
    when(() => repo.login(email: any(named: 'email'), password: any(named: 'password')))
        .thenAnswer((_) async => _user);
    final c = _containerWith(repo);

    await c.read(authViewModelProvider.future); // initial build
    await c.read(authViewModelProvider.notifier).login(email: 'a@b.com', password: 's3cret!');

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
}

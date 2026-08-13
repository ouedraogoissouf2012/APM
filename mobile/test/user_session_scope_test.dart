// Regression guard for #373: proves the MECHANISM UserSessionScope relies
// on — not just that the app's 9 hardcoded providers happen to reset today.
// A synthetic counter provider stands in for "the next per-user provider
// someone adds": if adding it to `overrides` is enough for it to be
// automatically reset when the signed-in user changes, then the day someone
// adds a real 10th per-user provider to main.dart's userScopedProviders,
// they get this guarantee for free — no `ref.invalidate` list to also
// remember, which is exactly the class of bug #373 closes (a provider added
// to the invalidate list would previously be forgotten, leaking the
// previous account's state to the next one on a shared device, #348).
import 'package:apm/main.dart';
import 'package:apm/src/data/models/app_user.dart';
import 'package:apm/src/ui/auth/view_model/auth_view_model.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

const _userA = AppUser(
  id: 1,
  email: 'a@b.com',
  nativeLanguage: 'fr',
  cefrLevel: 'A1',
  tier: 'free',
);

const _userB = AppUser(
  id: 2,
  email: 'b@b.com',
  nativeLanguage: 'fr',
  cefrLevel: 'A1',
  tier: 'free',
);

/// A controllable stand-in for the real AuthViewModel, so the test can drive
/// sign-in/sign-out without a real AuthRepository. Must extend
/// [AuthViewModel] itself (not just implement `AsyncNotifier<AppUser?>`) —
/// `authViewModelProvider.overrideWith` is typed to that exact Notifier
/// class, mirroring how a genuine AsyncNotifierProvider override works in
/// production, not a looser fake.
class _FakeAuthViewModel extends AuthViewModel {
  @override
  Future<AppUser?> build() async => null;

  void signIn(AppUser user) => state = AsyncData(user);

  void signOut() => state = const AsyncData(null);
}

/// Stands in for "a per-user provider" (e.g. profileViewModelProvider):
/// plain, non-autoDispose state that would otherwise happily survive across
/// accounts if nothing tore its container down.
final _counterProvider = NotifierProvider<_Counter, int>(_Counter.new);

class _Counter extends Notifier<int> {
  @override
  int build() => 0;

  void increment() => state++;
}

class _CounterView extends ConsumerWidget {
  const _CounterView();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final count = ref.watch(_counterProvider);
    return Column(
      children: [
        Text('count: $count'),
        ElevatedButton(
          onPressed: () => ref.read(_counterProvider.notifier).increment(),
          child: const Text('increment'),
        ),
      ],
    );
  }
}

void main() {
  testWidgets(
    'a provider added to UserSessionScope.overrides resets automatically '
    'when the signed-in user changes (#373)',
    (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [authViewModelProvider.overrideWith(_FakeAuthViewModel.new)],
          child: MaterialApp(
            home: UserSessionScope(
              overrides: [_counterProvider],
              child: const _CounterView(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('count: 0'), findsOneWidget);
      await tester.tap(find.text('increment'));
      await tester.pump();
      await tester.tap(find.text('increment'));
      await tester.pump();
      expect(
        find.text('count: 2'),
        findsOneWidget,
        reason: 'sanity check: the counter is a real, live provider',
      );

      // The container that hosts the FAKE AuthViewModel lives ABOVE
      // UserSessionScope (it is NOT one of the user-scoped overrides), so
      // this reaches the same instance production code would drive via
      // AuthViewModel.login/logout. Cast to the fake's own type for
      // signIn/signOut — authViewModelProvider.notifier is statically typed
      // as the base AuthViewModel, which doesn't know about them.
      final outerContainer = ProviderScope.containerOf(
        tester.element(find.byType(UserSessionScope)),
      );
      final fakeAuth =
          outerContainer.read(authViewModelProvider.notifier)
              as _FakeAuthViewModel;

      fakeAuth.signIn(_userA);
      await tester.pumpAndSettle();

      expect(
        find.text('count: 0'),
        findsOneWidget,
        reason:
            'signing in changed the user id from null -> 1, which must key a '
            'FRESH per-user provider subtree even though this is the FIRST '
            'sign-in, not just a logout',
      );

      await tester.tap(find.text('increment'));
      await tester.pump();
      expect(find.text('count: 1'), findsOneWidget);

      // A DIFFERENT account signing in without an intermediate sign-out
      // (id 1 -> 2 directly) must also reset — the leak #348/#373 guard
      // against is cross-ACCOUNT bleed, not specifically the null<->id edge.
      fakeAuth.signIn(_userB);
      await tester.pumpAndSettle();

      expect(
        find.text('count: 0'),
        findsOneWidget,
        reason: 'a different account signing in must not inherit the '
            'previous account\'s per-user state',
      );

      await tester.tap(find.text('increment'));
      await tester.pump();
      expect(find.text('count: 1'), findsOneWidget);

      fakeAuth.signOut();
      await tester.pumpAndSettle();

      expect(
        find.text('count: 0'),
        findsOneWidget,
        reason: 'logout must reset the per-user provider back to its '
            'initial state — the actual #373 scenario',
      );
    },
  );
}

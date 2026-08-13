import 'dart:async';

import 'package:apm/src/core/router/debounced_push.dart';
import 'package:apm/src/core/router/routes.dart';
import 'package:apm/src/data/models/profile.dart';
import 'package:apm/src/data/repositories/profile_repository.dart';
import 'package:apm/src/ui/profile/view_model/profile_view_model.dart';
import 'package:apm/src/ui/profile/widgets/profile_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mocktail/mocktail.dart';

class _MockProfileRepository extends Mock implements ProfileRepository {}

Profile _profile() => const Profile(
  interests: ['football'],
  goal: 'job',
  correctionIntensity: 'gentle',
  accent: 'us',
);

Future<void> _pump(WidgetTester tester, ProfileRepository repo) async {
  final router = GoRouter(
    initialLocation: Routes.profile,
    routes: [
      GoRoute(path: Routes.profile, builder: (_, _) => const ProfileScreen()),
      GoRoute(
        path: Routes.voicePrivacy,
        builder: (_, _) => const Scaffold(body: Text('Voice privacy target')),
      ),
    ],
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: [profileRepositoryProvider.overrideWithValue(repo)],
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  // Shared, single-instance guard (#331) — see debounced_push.dart's own doc
  // comment on why tests must reset it. A FIXED clock also makes the
  // double-tap test below immune to real elapsed time on a slow CI runner.
  setUp(() => debugResetDebouncedPushGuard(DebouncedPushGuard(clock: () => DateTime(2026))));

  late _MockProfileRepository repo;

  setUp(() {
    repo = _MockProfileRepository();
    when(repo.getProfile).thenAnswer((_) async => _profile());
  });

  testWidgets('the voice privacy link opens "ma voix & confidentialité"',
      (tester) async {
    await _pump(tester, repo);
    await tester.tap(find.byKey(const Key('voice_privacy_link')));
    await tester.pumpAndSettle();
    expect(find.text('Voice privacy target'), findsOneWidget);
  });

  testWidgets('a rapid double-tap on the voice privacy link pushes only once '
      '(#331)', (tester) async {
    await _pump(tester, repo);
    final link = find.byKey(const Key('voice_privacy_link'));
    await tester.tap(link);
    await tester.tap(link);
    await tester.pumpAndSettle();
    expect(find.text('Voice privacy target'), findsOneWidget);

    Navigator.of(tester.element(find.text('Voice privacy target'))).pop();
    await tester.pumpAndSettle();

    expect(find.text('Voice privacy target'), findsNothing);
    expect(find.byKey(const Key('voice_privacy_link')), findsOneWidget);
  });

  testWidgets('a rapid double-tap on "Enregistrer" saves only once (#352)', (
    tester,
  ) async {
    final saveGate = Completer<Profile>();
    when(
      () => repo.updateProfile(
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
        correctionIntensity: any(named: 'correctionIntensity'),
        accent: any(named: 'accent'),
        memorySummary: any(named: 'memorySummary'),
      ),
    ).thenAnswer((_) => saveGate.future);
    await _pump(tester, repo);

    final button = find.byKey(const Key('save_profile_button'));
    await tester.tap(button); // starts the save, _saving becomes true
    await tester.pump();
    await tester.tap(button); // guarded: onPressed is null while _saving
    await tester.pump();

    saveGate.complete(_profile());
    await tester.pumpAndSettle();

    verify(
      () => repo.updateProfile(
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
        correctionIntensity: any(named: 'correctionIntensity'),
        accent: any(named: 'accent'),
        memorySummary: any(named: 'memorySummary'),
      ),
    ).called(1);
  });
}

import 'package:apm/src/data/models/profile.dart';
import 'package:apm/src/data/repositories/profile_repository.dart';
import 'package:apm/src/ui/profile/view_model/profile_view_model.dart';
import 'package:apm/src/ui/profile/widgets/memory_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockProfileRepository extends Mock implements ProfileRepository {}

Profile _profile({String memory = ''}) => Profile(
  interests: const ['football'],
  goal: 'job',
  correctionIntensity: 'gentle',
  accent: 'us',
  memorySummary: memory,
);

Future<void> _pump(WidgetTester tester, ProfileRepository repo) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [profileRepositoryProvider.overrideWithValue(repo)],
      child: const MaterialApp(home: MemoryScreen()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() {
    registerFallbackValue(_profile());
  });

  testWidgets('shows the current memory summary in the field', (tester) async {
    final repo = _MockProfileRepository();
    when(
      repo.getProfile,
    ).thenAnswer((_) async => _profile(memory: 'Loves cooking and hiking.'));

    await _pump(tester, repo);

    expect(find.text('Loves cooking and hiking.'), findsOneWidget);
    // With content, "forget everything" is available.
    final clearBtn = tester.widget<TextButton>(
      find.byKey(const Key('clear_memory_button')),
    );
    expect(clearBtn.onPressed, isNotNull);
  });

  testWidgets('empty memory shows a hint and disables clearing', (tester) async {
    final repo = _MockProfileRepository();
    when(repo.getProfile).thenAnswer((_) async => _profile(memory: ''));

    await _pump(tester, repo);

    expect(find.byKey(const Key('memory_empty_hint')), findsOneWidget);
    final clearBtn = tester.widget<TextButton>(
      find.byKey(const Key('clear_memory_button')),
    );
    expect(clearBtn.onPressed, isNull); // nothing to clear
  });

  testWidgets('saving an edit calls the repository with the new text', (
    tester,
  ) async {
    final repo = _MockProfileRepository();
    when(repo.getProfile).thenAnswer((_) async => _profile(memory: 'old'));
    when(
      () => repo.updateProfile(
        interests: any(named: 'interests'),
        goal: any(named: 'goal'),
        correctionIntensity: any(named: 'correctionIntensity'),
        accent: any(named: 'accent'),
        memorySummary: any(named: 'memorySummary'),
      ),
    ).thenAnswer((_) async => _profile(memory: 'new memory'));

    await _pump(tester, repo);

    await tester.enterText(find.byKey(const Key('memory_field')), 'new memory');
    await tester.tap(find.byKey(const Key('save_memory_button')));
    await tester.pumpAndSettle();

    verify(() => repo.updateProfile(memorySummary: 'new memory')).called(1);
    expect(find.text('Mémoire enregistrée'), findsOneWidget); // honest feedback
  });

  testWidgets('error state shows a message, not a crash', (tester) async {
    final repo = _MockProfileRepository();
    when(repo.getProfile).thenThrow(Exception('network down'));

    await _pump(tester, repo);

    expect(find.byKey(const Key('memory_error')), findsOneWidget);
  });
}

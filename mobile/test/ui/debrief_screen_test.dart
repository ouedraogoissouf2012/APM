import 'package:apm/src/core/router/debounced_push.dart';
import 'package:apm/src/core/router/routes.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/data/models/debrief.dart';
import 'package:apm/src/data/models/review_item.dart';
import 'package:apm/src/ui/debrief/view_model/debrief_view_model.dart';
import 'package:apm/src/ui/debrief/widgets/debrief_screen.dart';
import 'package:apm/src/ui/review/view_model/review_view_model.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

Debrief _debrief({
  String cefr = 'B1',
  String summary = 'You spoke clearly and kept the conversation going.',
  List<DebriefError> errors = const [],
}) =>
    Debrief(cefrEstimate: cefr, summary: summary, errors: errors);

Future<void> _pump(
  WidgetTester tester,
  Debrief debrief, {
  List<ReviewItem> due = const [],
  String? scenarioId,
}) async {
  final router = GoRouter(
    initialLocation: '/debrief/1',
    routes: [
      GoRoute(
        path: Routes.debriefPattern,
        builder: (_, _) => DebriefScreen(sessionId: 1, scenarioId: scenarioId),
      ),
      GoRoute(
        path: Routes.home,
        builder: (_, _) => const Scaffold(body: Text('Home target')),
      ),
      GoRoute(
        path: Routes.echo,
        builder: (_, _) => const Scaffold(body: Text('Echo target')),
      ),
      GoRoute(
        path: Routes.review,
        builder: (_, _) => const Scaffold(body: Text('Review target')),
      ),
      GoRoute(
        path: Routes.proofPattern,
        builder: (_, _) => const Scaffold(body: Text('Proof target')),
      ),
    ],
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        debriefProvider(1).overrideWith((ref) async => debrief),
        reviewProvider.overrideWith((ref) async => due),
      ],
      child: MaterialApp.router(theme: AppTheme.dark(), routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  // The debounce guard (#331) is a single instance shared by the whole app, so
  // its state otherwise leaks across test cases: two tests pushing the same
  // route (several do, below — echo, review) within the cooldown of real
  // wall-clock test time would spuriously debounce each other. A FIXED clock
  // (not DateTime.now) also makes the double-tap tests below immune to a slow
  // CI runner: two tester.tap() calls always land at the "same instant" from
  // the guard's perspective, however long real elapsed time actually took.
  setUp(() => debugResetDebouncedPushGuard(DebouncedPushGuard(clock: () => DateTime(2026))));

  testWidgets('renders on the app dark surface — one consistent theme, no inversion',
      (tester) async {
    await _pump(tester, _debrief());
    // The debrief no longer inverts to a light "carnet": it shares the app's dark
    // theme so there is no jarring dark→light jump out of the conversation.
    final ctx = tester.element(find.byKey(const Key('cefr_estimate')));
    expect(Theme.of(ctx).brightness, Brightness.dark);
  });

  testWidgets('shows the CEFR level as the hero metric', (tester) async {
    await _pump(tester, _debrief(cefr: 'B2'));
    expect(find.byKey(const Key('cefr_estimate')), findsOneWidget);
    expect(find.text('B2'), findsOneWidget);
  });

  testWidgets('shows the summary under a "what worked" heading', (tester) async {
    await _pump(tester, _debrief(summary: 'Great flow and vocabulary.'));
    expect(find.text('Great flow and vocabulary.'), findsOneWidget);
    expect(find.text('CE QUI A MARCHÉ'), findsOneWidget);
  });

  testWidgets('lists corrections under "à reprendre" — struck original + fix',
      (tester) async {
    await _pump(
      tester,
      _debrief(errors: [
        const DebriefError(
          original: 'I have 25 years',
          correction: 'I am 25',
          rule: 'Age uses "to be" in English.',
          errorType: 'grammar',
        ),
      ]),
    );
    expect(find.text('À REPRENDRE'), findsOneWidget);
    expect(find.text('I have 25 years'), findsOneWidget);
    expect(find.text('I am 25'), findsOneWidget);
    expect(find.textContaining('to be'), findsOneWidget);
  });

  testWidgets('a correction shows its type, explanation, examples and options',
      (tester) async {
    await _pump(
      tester,
      _debrief(errors: [
        const DebriefError(
          original: 'i is happy',
          correction: 'I am happy',
          rule: "Use 'am' with 'I'.",
          errorType: 'subject_verb_agreement',
          explanation: "The verb must agree with the subject 'I'.",
          examples: ['I am tired.', 'I am ready.'],
          alternatives: ["I'm happy", 'I feel happy'],
        ),
      ]),
    );

    // error_type is surfaced (was parsed but never shown before), humanized.
    expect(find.text('SUBJECT VERB AGREEMENT'), findsOneWidget);
    // The fuller explanation and the grammar "options" are shown.
    expect(find.textContaining("must agree with the subject"), findsOneWidget);
    expect(find.text('EXEMPLES'), findsOneWidget);
    expect(find.text('· I am tired.'), findsOneWidget);
    expect(find.text('TU PEUX AUSSI DIRE'), findsOneWidget);
    expect(find.text("· I'm happy"), findsOneWidget);
  });

  testWidgets('no corrections shows an encouraging state, not an empty list',
      (tester) async {
    await _pump(tester, _debrief(errors: const []));
    expect(find.byKey(const Key('debrief_no_errors')), findsOneWidget);
  });

  testWidgets('the home button navigates back to home', (tester) async {
    await _pump(tester, _debrief());
    await tester.tap(find.byKey(const Key('debrief_home_button')));
    await tester.pumpAndSettle();
    expect(find.text('Home target'), findsOneWidget);
  });

  testWidgets('offers next steps: the debrief no longer dead-ends (#198)',
      (tester) async {
    await _pump(tester, _debrief());
    expect(find.text('ET MAINTENANT ?'), findsOneWidget);
    expect(find.byKey(const Key('debrief_next_echo')), findsOneWidget);
    expect(find.byKey(const Key('debrief_next_review')), findsOneWidget);
  });

  testWidgets('"m\'entraîner à prononcer" chains into the voice mirror (Écho)',
      (tester) async {
    await _pump(tester, _debrief());
    await tester.tap(find.byKey(const Key('debrief_next_echo')));
    await tester.pumpAndSettle();
    expect(find.text('Echo target'), findsOneWidget);
  });

  testWidgets('"réviser mes fautes" chains into the spaced review', (tester) async {
    await _pump(tester, _debrief());
    await tester.tap(find.byKey(const Key('debrief_next_review')));
    await tester.pumpAndSettle();
    expect(find.text('Review target'), findsOneWidget);
  });

  testWidgets('memory picks the next focus: the top due weakness is surfaced (#201)',
      (tester) async {
    await _pump(
      tester,
      _debrief(),
      due: const [
        ReviewItem(
          errorType: 'verb_tense',
          latestCorrection: 'I went',
          stage: 0,
          cleanStreak: 0,
          status: 'due',
        ),
        ReviewItem(
          errorType: 'article',
          latestCorrection: 'a cat',
          stage: 0,
          cleanStreak: 0,
          status: 'due',
        ),
      ],
    );

    // The FIRST due item is THE priority, humanised.
    final focus = find.byKey(const Key('debrief_priority_focus'));
    expect(focus, findsOneWidget);
    expect(find.text('Temps du verbe'), findsOneWidget); // verb_tense
    // Tapping it chains into the review.
    await tester.ensureVisible(focus);
    await tester.tap(focus);
    await tester.pumpAndSettle();
    expect(find.text('Review target'), findsOneWidget);
  });

  testWidgets('no due items -> no priority focus (never an empty prompt)',
      (tester) async {
    await _pump(tester, _debrief(), due: const []);
    expect(find.byKey(const Key('debrief_priority_focus')), findsNothing);
  });

  testWidgets('a scenario debrief chains into "Ma preuve" (#198)', (tester) async {
    await _pump(tester, _debrief(), scenarioId: 'job_interview');
    final proof = find.byKey(const Key('debrief_next_proof'));
    expect(proof, findsOneWidget);
    await tester.ensureVisible(proof);
    await tester.tap(proof);
    await tester.pumpAndSettle();
    expect(find.text('Proof target'), findsOneWidget);
  });

  testWidgets('a free/mission debrief has no "Ma preuve" (no skill to prove) (#198)',
      (tester) async {
    await _pump(tester, _debrief()); // no scenarioId
    expect(find.byKey(const Key('debrief_next_proof')), findsNothing);
  });

  group('anti-double-tap on push navigation (#331)', () {
    testWidgets('a rapid double-tap on "m\'entraîner à prononcer" pushes only '
        'once — one pop returns straight to the debrief, not to a second '
        'stacked Echo screen', (tester) async {
      await _pump(tester, _debrief());
      final button = find.byKey(const Key('debrief_next_echo'));
      await tester.tap(button);
      await tester.tap(button); // the accidental second tap
      await tester.pumpAndSettle();
      expect(find.text('Echo target'), findsOneWidget);

      Navigator.of(tester.element(find.text('Echo target'))).pop();
      await tester.pumpAndSettle();

      expect(find.text('Echo target'), findsNothing); // not still stacked
      expect(find.byKey(const Key('cefr_estimate')), findsOneWidget); // back
    });

    testWidgets('a rapid double-tap on "réviser mes fautes" pushes only once',
        (tester) async {
      await _pump(tester, _debrief());
      final button = find.byKey(const Key('debrief_next_review'));
      await tester.tap(button);
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(find.text('Review target'), findsOneWidget);

      Navigator.of(tester.element(find.text('Review target'))).pop();
      await tester.pumpAndSettle();

      expect(find.text('Review target'), findsNothing);
      expect(find.byKey(const Key('cefr_estimate')), findsOneWidget);
    });

    testWidgets('a rapid double-tap on "ta priorité" pushes only once',
        (tester) async {
      await _pump(
        tester,
        _debrief(),
        due: const [
          ReviewItem(
            errorType: 'verb_tense',
            latestCorrection: 'I went',
            stage: 0,
            cleanStreak: 0,
            status: 'due',
          ),
        ],
      );
      final focus = find.byKey(const Key('debrief_priority_focus'));
      await tester.ensureVisible(focus);
      await tester.tap(focus);
      await tester.tap(focus);
      await tester.pumpAndSettle();
      expect(find.text('Review target'), findsOneWidget);

      Navigator.of(tester.element(find.text('Review target'))).pop();
      await tester.pumpAndSettle();

      expect(find.text('Review target'), findsNothing);
      expect(find.byKey(const Key('cefr_estimate')), findsOneWidget);
    });

    testWidgets('a rapid double-tap on "Ma preuve" pushes only once',
        (tester) async {
      await _pump(tester, _debrief(), scenarioId: 'job_interview');
      final proof = find.byKey(const Key('debrief_next_proof'));
      await tester.ensureVisible(proof);
      await tester.tap(proof);
      await tester.tap(proof);
      await tester.pumpAndSettle();
      expect(find.text('Proof target'), findsOneWidget);

      Navigator.of(tester.element(find.text('Proof target'))).pop();
      await tester.pumpAndSettle();

      expect(find.text('Proof target'), findsNothing);
      expect(find.byKey(const Key('cefr_estimate')), findsOneWidget);
    });
  });
}

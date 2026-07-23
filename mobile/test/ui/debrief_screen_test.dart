import 'package:apm/src/core/router/routes.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/data/models/debrief.dart';
import 'package:apm/src/ui/debrief/view_model/debrief_view_model.dart';
import 'package:apm/src/ui/debrief/widgets/debrief_screen.dart';
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

Future<void> _pump(WidgetTester tester, Debrief debrief) async {
  final router = GoRouter(
    initialLocation: '/debrief/1',
    routes: [
      GoRoute(
        path: Routes.debriefPattern,
        builder: (_, _) => const DebriefScreen(sessionId: 1),
      ),
      GoRoute(
        path: Routes.home,
        builder: (_, _) => const Scaffold(body: Text('Home target')),
      ),
    ],
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        debriefProvider(1).overrideWith((ref) async => debrief),
      ],
      child: MaterialApp.router(theme: AppTheme.dark(), routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('renders on the cream (light) surface — narrative inversion',
      (tester) async {
    await _pump(tester, _debrief());
    // The debrief content lives in light mode regardless of the app's dark
    // default — assert on a context BELOW the local Theme inversion.
    final ctx = tester.element(find.byKey(const Key('cefr_estimate')));
    expect(Theme.of(ctx).brightness, Brightness.light);
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
}

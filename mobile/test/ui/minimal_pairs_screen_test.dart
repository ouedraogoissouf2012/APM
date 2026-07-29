import 'package:apm/src/core/network/providers.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/data/models/minimal_pairs.dart';
import 'package:apm/src/data/repositories/minimal_pairs_repository.dart';
import 'package:apm/src/ui/minimal_pairs/view_model/minimal_pairs_state.dart';
import 'package:apm/src/ui/minimal_pairs/view_model/minimal_pairs_view_model.dart';
import 'package:apm/src/ui/minimal_pairs/widgets/minimal_pairs_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Stub with fixed state; lifecycle methods are no-ops so initState does nothing.
class _StubViewModel extends MinimalPairsViewModel {
  _StubViewModel(this._initial);
  final MinimalPairsState _initial;
  String? guessed;

  @override
  MinimalPairsState build() => _initial;
  @override
  Future<void> loadPair() async {}
  @override
  void markUnavailable() {}
  @override
  void guess(String word) => guessed = word;
  @override
  Future<void> playWord() async {}
}

const _pair = MinimalPair(
  id: 'ship_sheep',
  wordA: 'ship',
  wordB: 'sheep',
  sound: '/ɪ/ vs /iː/',
  tip: 'court vs long',
);

Future<_StubViewModel> _pump(
  WidgetTester tester,
  MinimalPairsState state, {
  bool serverTts = true,
  bool serverStt = true,
}) async {
  final stub = _StubViewModel(state);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        minimalPairsViewModelProvider.overrideWith(() => stub),
        serverTtsProvider.overrideWith((ref) async => serverTts),
        serverSttProvider.overrideWith((ref) async => serverStt),
      ],
      child: MaterialApp(theme: AppTheme.dark(), home: const MinimalPairsScreen()),
    ),
  );
  await tester.pump(const Duration(milliseconds: 100));
  return stub;
}

void main() {
  testWidgets('discrimination shows both choice buttons', (tester) async {
    await _pump(
      tester,
      const MinimalPairsState(
        phase: PairPhase.guessing,
        pair: _pair,
        spokenWord: 'sheep',
        spokenAudioB64: 'X',
      ),
    );
    expect(find.byKey(const Key('choice_ship')), findsOneWidget);
    expect(find.byKey(const Key('choice_sheep')), findsOneWidget);
  });

  testWidgets('tapping a choice records the guess', (tester) async {
    final stub = await _pump(
      tester,
      const MinimalPairsState(
        phase: PairPhase.guessing,
        pair: _pair,
        spokenWord: 'sheep',
        spokenAudioB64: 'X',
      ),
    );
    await tester.tap(find.byKey(const Key('choice_ship')));
    expect(stub.guessed, 'ship');
  });

  testWidgets('after a guess, shows feedback and a produce button', (tester) async {
    await _pump(
      tester,
      const MinimalPairsState(
        phase: PairPhase.guessed,
        pair: _pair,
        spokenWord: 'sheep',
        guess: 'sheep',
      ),
    );
    expect(find.byKey(const Key('pairs_guess_feedback')), findsOneWidget);
  });

  testWidgets('reviewing shows the production verdict', (tester) async {
    await _pump(
      tester,
      const MinimalPairsState(
        phase: PairPhase.reviewing,
        pair: _pair,
        spokenWord: 'sheep',
        attempt: PairAttempt(
          transcript: 'ship',
          saidTarget: false,
          saidOther: true,
          coaching: 'Long ee.',
        ),
      ),
    );
    expect(find.byKey(const Key('pairs_verdict')), findsOneWidget);
    expect(find.byKey(const Key('pairs_coaching')), findsOneWidget);
  });

  testWidgets('shows unavailable when there is no server voice', (tester) async {
    await _pump(
      tester,
      const MinimalPairsState(unavailable: true),
      serverTts: false,
      serverStt: false,
    );
    expect(find.byKey(const Key('pairs_unavailable')), findsOneWidget);
  });
}

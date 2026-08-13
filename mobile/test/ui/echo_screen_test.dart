import 'dart:typed_data';

import 'package:apm/src/core/network/providers.dart';
import 'package:apm/src/data/models/echo.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/design_system/atoms/app_button.dart';
import 'package:apm/src/design_system/organisms/voice_orb.dart';
import 'package:apm/src/ui/echo/view_model/echo_state.dart';
import 'package:apm/src/ui/echo/view_model/echo_view_model.dart';
import 'package:apm/src/ui/echo/widgets/echo_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Stub view-model: fixed state, no network/mic. Its lifecycle methods are
/// no-ops so initState's loadPhrase/markUnavailable don't do real work.
class _StubEchoViewModel extends EchoViewModel {
  _StubEchoViewModel(this._initial);
  final EchoState _initial;
  bool recordCalled = false;

  @override
  EchoState build() => _initial;
  @override
  Future<void> loadPhrase() async {}
  @override
  void markUnavailable() {}
  @override
  Future<void> record() async {
    recordCalled = true;
  }

  @override
  Future<void> playModel() async {}
}

Future<_StubEchoViewModel> _pump(
  WidgetTester tester,
  EchoState state, {
  bool serverTts = true,
  bool serverStt = true,
}) async {
  final stub = _StubEchoViewModel(state);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        echoViewModelProvider.overrideWith(() => stub),
        serverTtsProvider.overrideWith((ref) async => serverTts),
        serverSttProvider.overrideWith((ref) async => serverStt),
      ],
      child: MaterialApp(theme: AppTheme.dark(), home: const EchoScreen()),
    ),
  );
  await tester.pump(const Duration(milliseconds: 100));
  return stub;
}

void main() {
  const phrase = ShadowingPhrase(
    text: 'The ship is sinking',
    focus: 'ship_sheep',
    tip: 'short i',
  );

  testWidgets('shows the target phrase and the orb when a phrase is loaded', (
    tester,
  ) async {
    await _pump(tester, const EchoState(phrase: phrase, modelAudioB64: 'X'));

    expect(find.byKey(const Key('echo_phrase')), findsOneWidget);
    expect(find.byType(VoiceOrb), findsOneWidget);
    // OverlineText upper-cases its content, so match case-insensitively.
    expect(
      find.textContaining(RegExp('round 1 / 5', caseSensitive: false)),
      findsOneWidget,
    );
  });

  testWidgets('recording phase maps the orb to listening', (tester) async {
    await _pump(
      tester,
      const EchoState(
        phrase: phrase,
        modelAudioB64: 'X',
        phase: EchoPhase.recording,
      ),
    );
    final orb = tester.widget<VoiceOrb>(find.byType(VoiceOrb));
    expect(orb.state, VoiceOrbState.listening);
  });

  testWidgets('tapping the orb (idle) starts recording', (tester) async {
    final stub = await _pump(
      tester,
      const EchoState(phrase: phrase, modelAudioB64: 'X'),
    );
    await tester.tap(find.byKey(const Key('echo_orb')));
    expect(stub.recordCalled, isTrue);
  });

  testWidgets(
    'a11y (#329) : orbe idle expose un bouton nommé, activé, avec indice de tap',
    (tester) async {
      final handle = tester.ensureSemantics();
      await _pump(tester, const EchoState(phrase: phrase, modelAudioB64: 'X'));

      expect(
        tester.getSemantics(find.byKey(const Key('echo_orb'))),
        matchesSemantics(
          label: 'touche pour t’enregistrer',
          isButton: true,
          isEnabled: true,
          hasEnabledState: true,
          hasTapAction: true,
          onTapHint: 'enregistrer',
        ),
      );
      // The visible OverlineText caption below the orb repeats the SAME text
      // on purpose (the issue asks to reuse it) — it must be excluded from the
      // semantics tree, or a screen reader would announce the identical phrase
      // twice in a row. Case-insensitive: OverlineText.toUpperCase()s its
      // content by design (DESIGN_SPEC §3).
      expect(
        find.bySemanticsLabel(
          RegExp('touche pour t’enregistrer', caseSensitive: false),
        ),
        findsOneWidget,
      );

      handle.dispose();
    },
  );

  testWidgets('a11y (#329) : orbe recording activé, label + indice changent', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    await _pump(
      tester,
      const EchoState(
        phrase: phrase,
        modelAudioB64: 'X',
        phase: EchoPhase.recording,
      ),
    );

    expect(
      tester.getSemantics(find.byKey(const Key('echo_orb'))),
      matchesSemantics(
        label: 'je t’écoute — touche pour arrêter',
        isButton: true,
        isEnabled: true,
        hasEnabledState: true,
        hasTapAction: true,
        onTapHint: 'arrêter',
      ),
    );

    handle.dispose();
  });

  testWidgets(
    'a11y (#329) : orbe reviewing reste activé (ré-enregistrer par-dessus '
    'le bilan est un choix voulu — record() gère la transition)',
    (tester) async {
      final handle = tester.ensureSemantics();
      await _pump(
        tester,
        EchoState(
          phrase: phrase,
          modelAudioB64: 'X',
          phase: EchoPhase.reviewing,
          result: const AttemptResult(transcript: 'the ship is sinking'),
        ),
      );

      expect(
        tester.getSemantics(find.byKey(const Key('echo_orb'))),
        matchesSemantics(
          label: 'compare ta voix au modèle',
          isButton: true,
          isEnabled: true,
          hasEnabledState: true,
          hasTapAction: true,
          onTapHint: 'enregistrer',
        ),
      );

      handle.dispose();
    },
  );

  testWidgets(
    'a11y (#329) : orbe scoring (analyse en cours, non interruptible) '
    'désactivé, sans indice de tap',
    (tester) async {
      final handle = tester.ensureSemantics();
      await _pump(
        tester,
        const EchoState(
          phrase: phrase,
          modelAudioB64: 'X',
          phase: EchoPhase.scoring,
        ),
      );

      expect(
        tester.getSemantics(find.byKey(const Key('echo_orb'))),
        matchesSemantics(
          label: 'analyse de tes sons…',
          isButton: true,
          isEnabled: false,
          hasEnabledState: true,
          hasTapAction: false,
          // onTapHint compiles to a custom semantics action (Flutter's
          // matchesSemantics only checks it when a value is passed here) — an
          // explicit empty list is what actually proves NO hint survived,
          // matching this test's own title ("sans indice de tap").
          customActions: const <CustomSemanticsAction>[],
        ),
      );

      handle.dispose();
    },
  );

  testWidgets(
    'after scoring, shows A/B buttons and the coaching once it arrives',
    (tester) async {
      await _pump(
        tester,
        EchoState(
          phrase: phrase,
          phase: EchoPhase.reviewing,
          result: const AttemptResult(
            transcript: 'the sheep is sinking',
            missedWords: ['ship'],
          ),
          // Coaching arrives via a separate deferred call -> lives on the state.
          coaching: 'Short i in ship.',
        ),
      );
      expect(find.text('Modèle'), findsOneWidget);
      expect(find.text('Ma voix'), findsOneWidget);
      expect(find.byKey(const Key('echo_coaching')), findsOneWidget);
    },
  );

  testWidgets(
    'code review (#330): the A/B buttons are disabled during a re-attempt, '
    'even though the stale result from the PREVIOUS attempt is still on state',
    (tester) async {
      // orbTap maps `reviewing` -> record() (echo_screen.dart), which starts a
      // fresh recording WITHOUT clearing `result` — so this is a state a real
      // re-attempt actually reaches, not a synthetic one. Without gating on
      // `phase == reviewing`, "Modèle" would play synthesized audio through the
      // speaker while the mic is actively capturing the new attempt.
      await _pump(
        tester,
        EchoState(
          phrase: phrase,
          phase: EchoPhase.recording,
          result: const AttemptResult(
            transcript: 'the sheep is sinking',
            missedWords: ['ship'],
          ),
        ),
      );

      final modele = tester.widget<AppButton>(
        find.widgetWithText(AppButton, 'Modèle'),
      );
      final maVoix = tester.widget<AppButton>(
        find.widgetWithText(AppButton, 'Ma voix'),
      );
      expect(modele.onPressed, isNull);
      expect(maVoix.onPressed, isNull);
    },
  );

  testWidgets(
    'code review (#330 followup): Modèle is disabled while Ma voix is '
    'playing (EchoPhase.playingMine) — the two share one speaker',
    (tester) async {
      // playMine() transitions through its own EchoPhase.playingMine while
      // it plays (mirroring playModel()'s playingModel), so the SAME
      // `phase == reviewing` gate that already covers "recording" above also
      // covers this — without it, tapping "Modèle" here would cut "Ma voix"
      // off mid-clip through the shared audio player.
      await _pump(
        tester,
        EchoState(
          phrase: phrase,
          phase: EchoPhase.playingMine,
          result: const AttemptResult(transcript: 'the ship is sinking'),
          myRecording: Uint8List.fromList(const [1, 2, 3]),
        ),
      );

      final modele = tester.widget<AppButton>(
        find.widgetWithText(AppButton, 'Modèle'),
      );
      final maVoix = tester.widget<AppButton>(
        find.widgetWithText(AppButton, 'Ma voix'),
      );
      expect(modele.onPressed, isNull);
      expect(maVoix.onPressed, isNull); // already playing — not re-tappable
    },
  );

  testWidgets(
    'final review sweep: "Phrase suivante" is disabled while Modèle/Ma voix '
    'is playing, not just while the orb is mid-attempt',
    (tester) async {
      // nextRound() races loadPhrase() against the SAME busy guard playback
      // holds (see the nextRound() doc comment in echo_view_model.dart) —
      // without this gate, tapping through would silently advance the round
      // counter while the phrase/result stayed the previous round's.
      await _pump(
        tester,
        EchoState(
          phrase: phrase,
          phase: EchoPhase.playingModel,
          result: const AttemptResult(transcript: 'the ship is sinking'),
        ),
      );

      final next = tester.widget<AppButton>(
        find.widgetWithText(AppButton, 'Phrase suivante'),
      );
      expect(next.onPressed, isNull);
    },
  );

  testWidgets('shows a coaching loader while the deferred tip is in flight', (
    tester,
  ) async {
    await _pump(
      tester,
      EchoState(
        phrase: phrase,
        phase: EchoPhase.reviewing,
        result: const AttemptResult(
          transcript: 'the sheep is sinking',
          missedWords: ['ship'],
        ),
        coachingLoading: true, // score already shown, coaching still loading
      ),
    );
    // The result (A/B) is already interactive; only the coaching is pending.
    expect(find.text('Modèle'), findsOneWidget);
    expect(find.byKey(const Key('echo_coaching_loading')), findsOneWidget);
    expect(find.byKey(const Key('echo_coaching')), findsNothing);
  });

  testWidgets('a perfect attempt shows the success message, no coaching box', (
    tester,
  ) async {
    await _pump(
      tester,
      const EchoState(
        phrase: phrase,
        phase: EchoPhase.reviewing,
        result: AttemptResult(transcript: 'the ship is sinking'),
      ),
    );
    expect(find.byKey(const Key('echo_perfect')), findsOneWidget);
    expect(find.byKey(const Key('echo_coaching')), findsNothing);
  });

  testWidgets('shows the unavailable message when there is no server voice', (
    tester,
  ) async {
    await _pump(
      tester,
      const EchoState(unavailable: true),
      serverTts: false,
      serverStt: false,
    );
    expect(find.byKey(const Key('echo_unavailable')), findsOneWidget);
  });

  testWidgets(
    'shows per-phoneme detail with an uncertainty note when GOP scores exist',
    (tester) async {
      await _pump(
        tester,
        EchoState(
          phrase: phrase,
          phase: EchoPhase.reviewing,
          result: const AttemptResult(
            transcript: 'think',
            phonemes: [
              EchoPhonemeScore(phoneme: 'θ', score: 0.08),
              EchoPhonemeScore(phoneme: 'k', score: 0.9),
            ],
          ),
        ),
      );
      expect(find.byKey(const Key('echo_phonemes')), findsOneWidget);
      // Each phoneme is shown in IPA slashes.
      expect(find.text('/θ/'), findsOneWidget);
      expect(find.text('/k/'), findsOneWidget);
      // The honest uncertainty note is always present (tracked debt: uncalibrated).
      expect(
        find.byKey(const Key('echo_phonemes_uncertainty')),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'shows no phoneme detail when GOP scores are absent (fake engine)',
    (tester) async {
      await _pump(
        tester,
        const EchoState(
          phrase: phrase,
          phase: EchoPhase.reviewing,
          result: AttemptResult(transcript: 'the ship is sinking'),
        ),
      );
      expect(find.byKey(const Key('echo_phonemes')), findsNothing);
    },
  );

  testWidgets('colors words by pronunciation score after scoring', (
    tester,
  ) async {
    await _pump(
      tester,
      EchoState(
        phrase: phrase,
        phase: EchoPhase.reviewing,
        result: const AttemptResult(
          transcript: 'the sheep is sinking',
          words: [
            ShadowingWord(
              target: 'The',
              heard: true,
              score: 0.95,
              confidence: 0.8,
            ),
            ShadowingWord(
              target: 'ship',
              heard: false,
              score: 0.0,
              confidence: 0.8,
            ),
            ShadowingWord(
              target: 'is',
              heard: true,
              score: 0.9,
              confidence: 0.8,
            ),
            ShadowingWord(
              target: 'sinking',
              heard: true,
              score: 0.9,
              confidence: 0.8,
            ),
          ],
          missedWords: ['ship'],
          coaching: 'Short i in ship.',
        ),
      ),
    );
    // The phrase renders as rich text with per-word colored spans.
    final richText = tester.widget<Text>(find.byKey(const Key('echo_phrase')));
    final span = richText.textSpan! as TextSpan;
    final children = span.children!.cast<TextSpan>();
    // "ship" (score 0) is colored (needs-practice); a well-scored word too, but
    // both differ from the default (null-styled) spacing spans.
    final shipSpan = children.firstWhere((s) => s.text == 'ship');
    expect(shipSpan.style?.color, isNotNull);
  });
}

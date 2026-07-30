import 'package:apm/src/core/network/providers.dart';
import 'package:apm/src/data/models/echo.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/design_system/organisms/voice_orb.dart';
import 'package:apm/src/ui/echo/view_model/echo_state.dart';
import 'package:apm/src/ui/echo/view_model/echo_view_model.dart';
import 'package:apm/src/ui/echo/widgets/echo_screen.dart';
import 'package:flutter/material.dart';
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
  const phrase = ShadowingPhrase(text: 'The ship is sinking', focus: 'ship_sheep', tip: 'short i');

  testWidgets('shows the target phrase and the orb when a phrase is loaded', (tester) async {
    await _pump(tester, const EchoState(phrase: phrase, modelAudioB64: 'X'));

    expect(find.byKey(const Key('echo_phrase')), findsOneWidget);
    expect(find.byType(VoiceOrb), findsOneWidget);
    // OverlineText upper-cases its content, so match case-insensitively.
    expect(find.textContaining(RegExp('round 1 / 5', caseSensitive: false)), findsOneWidget);
  });

  testWidgets('recording phase maps the orb to listening', (tester) async {
    await _pump(
      tester,
      const EchoState(phrase: phrase, modelAudioB64: 'X', phase: EchoPhase.recording),
    );
    final orb = tester.widget<VoiceOrb>(find.byType(VoiceOrb));
    expect(orb.state, VoiceOrbState.listening);
  });

  testWidgets('tapping the orb (idle) starts recording', (tester) async {
    final stub = await _pump(tester, const EchoState(phrase: phrase, modelAudioB64: 'X'));
    await tester.tap(find.byKey(const Key('echo_orb')));
    expect(stub.recordCalled, isTrue);
  });

  testWidgets('after scoring, shows A/B buttons and coaching', (tester) async {
    await _pump(
      tester,
      EchoState(
        phrase: phrase,
        phase: EchoPhase.reviewing,
        result: const AttemptResult(
          transcript: 'the sheep is sinking',
          missedWords: ['ship'],
          coaching: 'Short i in ship.',
        ),
      ),
    );
    expect(find.text('Modèle'), findsOneWidget);
    expect(find.text('Ma voix'), findsOneWidget);
    expect(find.byKey(const Key('echo_coaching')), findsOneWidget);
  });

  testWidgets('a perfect attempt shows the success message, no coaching box', (tester) async {
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

  testWidgets('shows the unavailable message when there is no server voice', (tester) async {
    await _pump(
      tester,
      const EchoState(unavailable: true),
      serverTts: false,
      serverStt: false,
    );
    expect(find.byKey(const Key('echo_unavailable')), findsOneWidget);
  });

  testWidgets('shows per-phoneme detail with an uncertainty note when GOP scores exist',
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
    expect(find.byKey(const Key('echo_phonemes_uncertainty')), findsOneWidget);
  });

  testWidgets('shows no phoneme detail when GOP scores are absent (fake engine)',
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
  });

  testWidgets('colors words by pronunciation score after scoring', (tester) async {
    await _pump(
      tester,
      EchoState(
        phrase: phrase,
        phase: EchoPhase.reviewing,
        result: const AttemptResult(
          transcript: 'the sheep is sinking',
          words: [
            ShadowingWord(target: 'The', heard: true, score: 0.95, confidence: 0.8),
            ShadowingWord(target: 'ship', heard: false, score: 0.0, confidence: 0.8),
            ShadowingWord(target: 'is', heard: true, score: 0.9, confidence: 0.8),
            ShadowingWord(target: 'sinking', heard: true, score: 0.9, confidence: 0.8),
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

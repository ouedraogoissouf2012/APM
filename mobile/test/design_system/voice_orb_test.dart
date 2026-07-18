import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/design_system/organisms/voice_orb.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _harness(Widget child, {bool disableAnimations = false}) => MaterialApp(
      theme: AppTheme.dark(),
      home: MediaQuery(
        data: MediaQueryData(disableAnimations: disableAnimations),
        child: Scaffold(body: Center(child: child)),
      ),
    );

void main() {
  testWidgets('idle : icône micro, pas de waveform ni d\'anneaux',
      (tester) async {
    await tester.pumpWidget(_harness(
      const VoiceOrb(state: VoiceOrbState.idle),
    ));
    expect(find.byIcon(Icons.mic), findsOneWidget);
    expect(find.byKey(const Key('orb_bar_0')), findsNothing);
    expect(find.byKey(const Key('orb_ring_0')), findsNothing);
    // Rien n'anime : pumpAndSettle doit converger.
    await tester.pumpAndSettle();
  });

  testWidgets('listening : 5 barres de waveform + 2 anneaux de propagation',
      (tester) async {
    await tester.pumpWidget(_harness(
      const VoiceOrb(state: VoiceOrbState.listening),
    ));
    for (var i = 0; i < 5; i++) {
      expect(find.byKey(Key('orb_bar_$i')), findsOneWidget);
    }
    expect(find.byKey(const Key('orb_ring_0')), findsOneWidget);
    expect(find.byKey(const Key('orb_ring_1')), findsOneWidget);
    expect(find.byIcon(Icons.mic), findsNothing);
  });

  testWidgets('thinking : 3 points pulsants à la place de la waveform',
      (tester) async {
    await tester.pumpWidget(_harness(
      const VoiceOrb(state: VoiceOrbState.thinking),
    ));
    for (var i = 0; i < 3; i++) {
      expect(find.byKey(Key('orb_dot_$i')), findsOneWidget);
    }
    expect(find.byKey(const Key('orb_bar_0')), findsNothing);
  });

  testWidgets('speaking : waveform affichée', (tester) async {
    await tester.pumpWidget(_harness(
      const VoiceOrb(state: VoiceOrbState.speaking, amplitude: 0.8),
    ));
    expect(find.byKey(const Key('orb_bar_0')), findsOneWidget);
  });

  testWidgets('taille paramétrable (défaut 170)', (tester) async {
    await tester.pumpWidget(_harness(
      const VoiceOrb(state: VoiceOrbState.idle),
    ));
    expect(tester.getSize(find.byType(VoiceOrb)), const Size(170, 170));

    await tester.pumpWidget(_harness(
      const VoiceOrb(state: VoiceOrbState.idle, size: 120),
    ));
    expect(tester.getSize(find.byType(VoiceOrb)), const Size(120, 120));
  });

  testWidgets('la waveform anime réellement (scaleY varie entre deux pumps)',
      (tester) async {
    await tester.pumpWidget(_harness(
      const VoiceOrb(state: VoiceOrbState.listening),
    ));

    double heightOf() =>
        tester.getSize(find.byKey(const Key('orb_bar_0'))).height;

    final before = heightOf();
    await tester.pump(const Duration(milliseconds: 400));
    final after = heightOf();
    expect(before, isNot(after));
  });

  testWidgets(
      'accessibilité : animations désactivées → rendu statique stable',
      (tester) async {
    await tester.pumpWidget(_harness(
      const VoiceOrb(state: VoiceOrbState.listening),
      disableAnimations: true,
    ));
    // Aucun contrôleur ne tourne : pumpAndSettle converge.
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('orb_bar_0')), findsOneWidget);
  });

  testWidgets('changement d\'état à chaud : listening → thinking → idle',
      (tester) async {
    await tester.pumpWidget(_harness(
      const VoiceOrb(state: VoiceOrbState.listening),
    ));
    expect(find.byKey(const Key('orb_bar_0')), findsOneWidget);

    await tester.pumpWidget(_harness(
      const VoiceOrb(state: VoiceOrbState.thinking),
    ));
    expect(find.byKey(const Key('orb_dot_0')), findsOneWidget);

    await tester.pumpWidget(_harness(
      const VoiceOrb(state: VoiceOrbState.idle),
    ));
    expect(find.byIcon(Icons.mic), findsOneWidget);
    await tester.pumpAndSettle();
  });
}

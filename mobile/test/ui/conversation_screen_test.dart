import 'package:apm/src/core/router/routes.dart';
import 'package:apm/src/core/theme/app_theme.dart';
import 'package:apm/src/data/models/session_modes.dart';
import 'package:apm/src/data/models/turn_correction.dart';
import 'package:apm/src/design_system/molecules/correction_chip.dart';
import 'package:apm/src/design_system/molecules/transcript_text.dart';
import 'package:apm/src/design_system/organisms/voice_orb.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_state.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_view_model.dart';
import 'package:apm/src/ui/conversation/widgets/conversation_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

/// Stub : état fixe injecté, aucune dépendance réseau/micro.
class _StubConversationViewModel extends ConversationViewModel {
  _StubConversationViewModel(this._initial);

  final ConversationState _initial;
  bool listenCalled = false;
  bool stopCalled = false;
  bool endCalled = false;

  @override
  ConversationState build() => _initial;

  @override
  Future<void> start({
    String mode = kSessionModeFree,
    String? scenarioId,
  }) async {}

  @override
  Future<void> listenAndRespond() async {
    listenCalled = true;
  }

  @override
  Future<void> stopConversation() async {
    stopCalled = true;
  }

  @override
  Future<void> end() async {
    endCalled = true;
    state = const ConversationState();
  }
}

Future<_StubConversationViewModel> _pump(
  WidgetTester tester,
  ConversationState state, {
  String location = '/conversation?mode=free',
}) async {
  final stub = _StubConversationViewModel(state);
  final router = GoRouter(
    initialLocation: location,
    routes: [
      GoRoute(
        path: Routes.conversation,
        builder: (_, _) => const ConversationScreen(),
      ),
      GoRoute(
        path: Routes.home,
        builder: (_, _) => const Scaffold(body: Text('Home target')),
      ),
      GoRoute(
        path: Routes.debriefPattern,
        builder: (_, _) => const Scaffold(body: Text('Debrief target')),
      ),
    ],
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: [conversationViewModelProvider.overrideWith(() => stub)],
      child: MaterialApp.router(theme: AppTheme.dark(), routerConfig: router),
    ),
  );
  await tester.pump(const Duration(milliseconds: 100));
  return stub;
}

void main() {
  const activeIdle = ConversationState(
    sessionId: 7,
    turns: [ConversationTurn(kRoleAssistant, "Hi, let's practise English.")],
  );

  testWidgets('idle : orbe en idle, invite à parler, tap → listenAndRespond',
      (tester) async {
    final stub = await _pump(tester, activeIdle);

    final orb = tester.widget<VoiceOrb>(find.byType(VoiceOrb));
    expect(orb.state, VoiceOrbState.idle);
    expect(find.text("TOUCHE L'ORBE POUR PARLER"), findsOneWidget);

    await tester.tap(find.byKey(const Key('mic_button')));
    expect(stub.listenCalled, isTrue);
  });

  testWidgets('listening : orbe en écoute + overline JE T\'ÉCOUTE',
      (tester) async {
    await _pump(
      tester,
      activeIdle.copyWith(status: ConversationStatus.listening),
    );
    expect(
      tester.widget<VoiceOrb>(find.byType(VoiceOrb)).state,
      VoiceOrbState.listening,
    );
    expect(find.textContaining("JE T'ÉCOUTE"), findsOneWidget);
  });

  testWidgets('tapping the orb while listening stops the conversation',
      (tester) async {
    final stub = await _pump(
      tester,
      activeIdle.copyWith(status: ConversationStatus.listening),
    );

    await tester.tap(find.byKey(const Key('mic_button')));
    expect(stub.stopCalled, isTrue);
    expect(stub.listenCalled, isFalse);
  });

  testWidgets('shows the live partial transcript while listening',
      (tester) async {
    await _pump(
      tester,
      activeIdle.copyWith(
        status: ConversationStatus.listening,
        partialTranscript: 'i would like to',
      ),
    );
    expect(find.byType(TranscriptText), findsOneWidget);
    expect(find.textContaining('i would like to'), findsOneWidget);
  });

  testWidgets('thinking/speaking : états mappés + réponse IA en sous-titre',
      (tester) async {
    const withReply = ConversationState(
      sessionId: 7,
      status: ConversationStatus.speaking,
      turns: [
        ConversationTurn(kRoleUser, 'I went to the market'),
        ConversationTurn(kRoleAssistant, 'Nice! What did you buy?'),
      ],
    );
    await _pump(tester, withReply);

    expect(
      tester.widget<VoiceOrb>(find.byType(VoiceOrb)).state,
      VoiceOrbState.speaking,
    );
    expect(find.text('Nice! What did you buy?'), findsOneWidget);
  });

  testWidgets('la dernière phrase de l\'apprenant s\'affiche en transcript',
      (tester) async {
    const spoke = ConversationState(
      sessionId: 7,
      turns: [
        ConversationTurn(kRoleAssistant, 'Hello!'),
        ConversationTurn(kRoleUser, 'I have been busy today'),
      ],
    );
    await _pump(tester, spoke);

    expect(find.byType(TranscriptText), findsOneWidget);
    expect(
      find.textContaining('« I have been busy today »'),
      findsOneWidget,
    );
  });

  testWidgets('pill de statut : sujet du scénario affiché', (tester) async {
    await _pump(
      tester,
      activeIdle,
      location: '/conversation?mode=scenario&scenario=job_interview',
    );
    expect(find.byKey(const Key('status_pill')), findsOneWidget);
    expect(find.text('Job interview'), findsOneWidget);
  });

  testWidgets('pill de statut : conversation libre par défaut',
      (tester) async {
    await _pump(tester, activeIdle);
    expect(find.text('Conversation libre'), findsOneWidget);
  });

  testWidgets('erreur affichée sans rouge (clé conversation_error)',
      (tester) async {
    await _pump(
      tester,
      activeIdle.copyWith(error: 'Could not get a reply'),
    );
    expect(find.byKey(const Key('conversation_error')), findsOneWidget);
    expect(find.text('Could not get a reply'), findsOneWidget);
  });

  testWidgets('fin de session : end() appelé puis navigation vers le bilan',
      (tester) async {
    final stub = await _pump(tester, activeIdle);

    await tester.tap(find.byKey(const Key('end_button')));
    // end() remet l'état à idle : plus aucune boucle, settle converge.
    await tester.pumpAndSettle();

    expect(stub.endCalled, isTrue);
    expect(find.text('Debrief target'), findsOneWidget);
  });

  testWidgets('correction : chip doré sous la bulle apprenant, tap → grammaire',
      (tester) async {
    const withCorrection = ConversationState(
      sessionId: 7,
      turns: [
        ConversationTurn(kRoleAssistant, 'Good.'),
        ConversationTurn(
          kRoleUser,
          'i is happy',
          correction: TurnCorrection(
            original: 'i is happy',
            correction: 'I am happy',
            rule: "Use 'am' with 'I'.",
            alternatives: ["I'm happy"],
          ),
        ),
      ],
    );
    await _pump(tester, withCorrection);
    // Let the chip's 400ms non-interruption delay elapse.
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byType(CorrectionChip), findsOneWidget);
    expect(find.byKey(const Key('turn_correction_chip')), findsOneWidget);

    await tester.tap(find.byKey(const Key('turn_correction_tap')));
    await tester.pumpAndSettle();

    // The grammar sheet shows the rule and the alternative phrasing.
    expect(find.byKey(const Key('grammar_sheet')), findsOneWidget);
    expect(find.text("Use 'am' with 'I'."), findsOneWidget);
    expect(find.textContaining("I'm happy"), findsWidgets);
  });

  testWidgets('correction : pas de chip pendant que l\'apprenant parle',
      (tester) async {
    const listeningWithCorrection = ConversationState(
      sessionId: 7,
      status: ConversationStatus.listening,
      partialTranscript: 'i is',
      turns: [
        ConversationTurn(
          kRoleUser,
          'i is happy',
          correction: TurnCorrection(
            original: 'i is happy',
            correction: 'I am happy',
            rule: 'r',
          ),
        ),
      ],
    );
    await _pump(tester, listeningWithCorrection);
    await tester.pump(const Duration(milliseconds: 500));

    // Non-interruption: the chip must not show while listening.
    expect(find.byType(CorrectionChip), findsNothing);
  });

  testWidgets('quota épuisé : affiche le paywall, pas l\'orbe', (tester) async {
    await _pump(
      tester,
      const ConversationState(quotaExhausted: true),
    );

    expect(find.byKey(const Key('quota_exhausted')), findsOneWidget);
    // No conversation UI when the session could not start.
    expect(find.byType(VoiceOrb), findsNothing);
    // A way out: back home.
    expect(find.byKey(const Key('quota_home_button')), findsOneWidget);
  });

  testWidgets('quota épuisé : le bouton ramène à l\'accueil', (tester) async {
    await _pump(
      tester,
      const ConversationState(quotaExhausted: true),
    );

    await tester.tap(find.byKey(const Key('quota_home_button')));
    await tester.pumpAndSettle();
    expect(find.text('Home target'), findsOneWidget);
  });
}

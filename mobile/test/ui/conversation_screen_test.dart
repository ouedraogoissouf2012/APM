import 'package:apm/src/core/network/providers.dart';
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
import 'package:flutter/semantics.dart';
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
  bool finishCalled = false;
  bool resumeCalled = false;
  bool replaceCalled = false;

  @override
  ConversationState build() => _initial;

  @override
  Future<void> start({
    String mode = kSessionModeFree,
    String? scenarioId,
    int? missionId,
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

  @override
  Future<void> finishCurrentUtterance() async {
    finishCalled = true;
  }

  @override
  Future<void> resumePending() async {
    resumeCalled = true;
  }

  @override
  Future<void> replacePending() async {
    replaceCalled = true;
  }
}

Future<_StubConversationViewModel> _pump(
  WidgetTester tester,
  ConversationState state, {
  String location = '/conversation?mode=free',
  bool demoMode = false,
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
      overrides: [
        conversationViewModelProvider.overrideWith(() => stub),
        demoModeProvider.overrideWith((ref) async => demoMode),
      ],
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

  testWidgets('idle : orbe en idle, invite à parler, tap → listenAndRespond', (
    tester,
  ) async {
    final stub = await _pump(tester, activeIdle);

    final orb = tester.widget<VoiceOrb>(find.byType(VoiceOrb));
    expect(orb.state, VoiceOrbState.idle);
    expect(find.text('PARLER'), findsOneWidget);

    await tester.tap(find.byKey(const Key('mic_button')));
    expect(stub.listenCalled, isTrue);
  });

  testWidgets(
    'a11y (#329) : orbe idle expose un bouton nommé, activé, avec indice de tap',
    (tester) async {
      final handle = tester.ensureSemantics();
      await _pump(tester, activeIdle);

      expect(
        tester.getSemantics(find.byKey(const Key('mic_button'))),
        matchesSemantics(
          label: 'Parler',
          isButton: true,
          isEnabled: true,
          hasEnabledState: true,
          hasTapAction: true,
          onTapHint: 'parler',
        ),
      );
      expect(
        find.bySemanticsLabel(RegExp('parler', caseSensitive: false)),
        findsOneWidget,
      );

      handle.dispose();
    },
  );

  testWidgets(
    'a11y (#329) : orbe listening reste un bouton activé, label + indice '
    'changent en conséquence',
    (tester) async {
      final handle = tester.ensureSemantics();
      await _pump(
        tester,
        activeIdle.copyWith(status: ConversationStatus.listening),
      );

      expect(
        tester.getSemantics(find.byKey(const Key('mic_button'))),
        matchesSemantics(
          label: 'Envoyer',
          isButton: true,
          isEnabled: true,
          hasEnabledState: true,
          hasTapAction: true,
          onTapHint: 'envoyer',
        ),
      );

      handle.dispose();
    },
  );

  testWidgets(
    'a11y (#496) : orbe thinking interruptible, label Interrompre',
    (tester) async {
      final handle = tester.ensureSemantics();
      await _pump(
        tester,
        activeIdle.copyWith(status: ConversationStatus.thinking),
      );

      expect(
        tester.getSemantics(find.byKey(const Key('mic_button'))),
        matchesSemantics(
          label: 'Interrompre',
          isButton: true,
          isEnabled: true,
          hasEnabledState: true,
          hasTapAction: true,
          onTapHint: 'interrompre',
        ),
      );

      handle.dispose();
    },
  );

  testWidgets(
    'a11y (#329) : session inactive (pas de sessionId) → orbe idle désactivé, '
    'label neutre (pas une invite à taper sur un contrôle désactivé)',
    (tester) async {
      final handle = tester.ensureSemantics();
      // isActive == false (sessionId null) even though status is idle — the
      // orb must not claim to be tappable before a session has started, NOR
      // announce the idle "touche l'orbe pour parler" instruction (that would
      // promise an action a screen-reader user can't actually trigger here).
      await _pump(tester, const ConversationState());

      expect(
        tester.getSemantics(find.byKey(const Key('mic_button'))),
        matchesSemantics(
          label: 'session en préparation',
          isButton: true,
          isEnabled: false,
          hasEnabledState: true,
          hasTapAction: false,
          customActions: const <CustomSemanticsAction>[],
        ),
      );

      handle.dispose();
    },
  );

  testWidgets('listening : orbe en écoute + overline ENVOYER', (tester) async {
    await _pump(
      tester,
      activeIdle.copyWith(status: ConversationStatus.listening),
    );
    expect(
      tester.widget<VoiceOrb>(find.byType(VoiceOrb)).state,
      VoiceOrbState.listening,
    );
    expect(find.text('ENVOYER'), findsOneWidget);
  });

  testWidgets('tapping the orb while listening sends the utterance', (
    tester,
  ) async {
    final stub = await _pump(
      tester,
      activeIdle.copyWith(status: ConversationStatus.listening),
    );

    await tester.tap(find.byKey(const Key('mic_button')));
    expect(stub.finishCalled, isTrue);
    expect(stub.stopCalled, isFalse);
    expect(stub.listenCalled, isFalse);
  });

  testWidgets('tapping the orb while thinking starts a new turn', (
    tester,
  ) async {
    final stub = await _pump(
      tester,
      activeIdle.copyWith(status: ConversationStatus.thinking),
    );

    await tester.tap(find.byKey(const Key('mic_button')));
    expect(stub.listenCalled, isTrue);
  });

  testWidgets('shows the live partial transcript while listening', (
    tester,
  ) async {
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

  testWidgets('thinking/speaking : états mappés + réponse IA en sous-titre', (
    tester,
  ) async {
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

  testWidgets('la dernière phrase de l\'apprenant s\'affiche en transcript', (
    tester,
  ) async {
    const spoke = ConversationState(
      sessionId: 7,
      turns: [
        ConversationTurn(kRoleAssistant, 'Hello!'),
        ConversationTurn(kRoleUser, 'I have been busy today'),
      ],
    );
    await _pump(tester, spoke);

    expect(find.byType(TranscriptText), findsOneWidget);
    expect(find.textContaining('« I have been busy today »'), findsOneWidget);
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

  testWidgets('pill de statut : conversation libre par défaut', (tester) async {
    await _pump(tester, activeIdle);
    expect(find.text('Conversation libre'), findsOneWidget);
  });

  testWidgets('erreur affichée sans rouge (clé conversation_error)', (
    tester,
  ) async {
    await _pump(tester, activeIdle.copyWith(error: 'Could not get a reply'));
    expect(find.byKey(const Key('conversation_error')), findsOneWidget);
    expect(find.text('Could not get a reply'), findsOneWidget);
  });

  testWidgets('fin de session : end() appelé puis navigation vers le bilan', (
    tester,
  ) async {
    final stub = await _pump(tester, activeIdle);

    await tester.tap(find.byKey(const Key('end_button')));
    // end() remet l'état à idle : plus aucune boucle, settle converge.
    await tester.pumpAndSettle();

    expect(stub.endCalled, isTrue);
    expect(find.text('Debrief target'), findsOneWidget);
  });

  testWidgets(
    'correction : chip doré sous la bulle apprenant, tap → grammaire',
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
    },
  );

  testWidgets('correction : pas de chip pendant que l\'apprenant parle', (
    tester,
  ) async {
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

  testWidgets('mode démo : bandeau affiché quand le backend est en fake', (
    tester,
  ) async {
    await _pump(tester, activeIdle, demoMode: true);
    await tester.pump();
    expect(find.byKey(const Key('demo_banner')), findsOneWidget);
    expect(find.textContaining('Mode démo'), findsOneWidget);
    expect(find.textContaining('DeepSeek'), findsNothing);
  });

  testWidgets('mode démo : aucun bandeau quand un vrai moteur est configuré', (
    tester,
  ) async {
    await _pump(tester, activeIdle, demoMode: false);
    await tester.pump();
    expect(find.byKey(const Key('demo_banner')), findsNothing);
  });

  testWidgets('quota : minutes restantes affichées pendant la session', (
    tester,
  ) async {
    await _pump(tester, activeIdle.copyWith(remainingMinutes: 7));
    expect(find.byKey(const Key('quota_remaining')), findsOneWidget);
    expect(find.text('7 min'), findsOneWidget);
    expect(find.byKey(const Key('quota_warning')), findsNothing);
  });

  testWidgets('quota : warning à 80 %', (tester) async {
    await _pump(
      tester,
      activeIdle.copyWith(remainingMinutes: 2, quotaWarning: true),
    );
    expect(find.byKey(const Key('quota_warning')), findsOneWidget);
  });

  testWidgets('Terminer : libellé visible et clé end_button inchangée', (
    tester,
  ) async {
    await _pump(tester, activeIdle);
    expect(find.byKey(const Key('end_button')), findsOneWidget);
    expect(find.text('Terminer'), findsOneWidget);
  });

  testWidgets('conflit 409 : affiche Reprendre et Terminer et recommencer', (
    tester,
  ) async {
    final stub = await _pump(
      tester,
      const ConversationState(sessionConflict: true),
    );

    expect(find.byKey(const Key('session_conflict')), findsOneWidget);
    expect(find.text('Une conversation est déjà en cours.'), findsOneWidget);
    expect(find.byType(VoiceOrb), findsNothing);
    expect(find.byKey(const Key('resume_session')), findsOneWidget);
    expect(find.byKey(const Key('replace_session')), findsOneWidget);
    expect(find.text('Reprendre'), findsOneWidget);
    expect(find.text('Terminer et recommencer'), findsOneWidget);

    await tester.tap(find.byKey(const Key('resume_session')));
    expect(stub.resumeCalled, isTrue);

    await tester.tap(find.byKey(const Key('replace_session')));
    expect(stub.replaceCalled, isTrue);
  });

  testWidgets('quota épuisé : affiche le paywall, pas l\'orbe', (tester) async {
    await _pump(tester, const ConversationState(quotaExhausted: true));

    expect(find.byKey(const Key('quota_exhausted')), findsOneWidget);
    // No conversation UI when the session could not start.
    expect(find.byType(VoiceOrb), findsNothing);
    // A way out: back home.
    expect(find.byKey(const Key('quota_home_button')), findsOneWidget);
  });

  testWidgets('quota épuisé : le bouton ramène à l\'accueil', (tester) async {
    await _pump(tester, const ConversationState(quotaExhausted: true));

    await tester.tap(find.byKey(const Key('quota_home_button')));
    await tester.pumpAndSettle();
    expect(find.text('Home target'), findsOneWidget);
  });
}

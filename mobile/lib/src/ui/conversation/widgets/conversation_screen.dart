import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/providers.dart';
import '../../../core/router/routes.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/ui/practice_screen_lifecycle.dart';
import '../../../data/models/scenarios.dart';
import '../../../data/models/session_modes.dart';
import '../../../data/models/turn_correction.dart';
import '../../../design_system/atoms/app_button.dart';
import '../../../design_system/atoms/overline_text.dart';
import '../../../design_system/molecules/correction_chip.dart';
import 'network_banner.dart';
import '../../../design_system/molecules/transcript_text.dart';
import '../../../design_system/organisms/voice_orb.dart';
import '../view_model/conversation_state.dart';
import '../view_model/conversation_view_model.dart';
import 'grammar_sheet.dart';
import 'session_status_pill.dart';

/// Écran conversation — le tunnel immersif du DESIGN_SPEC §6.1.
///
/// Pill de statut en haut, orbe vocal au centre (tap pour parler),
/// overline d'état, dernière phrase de l'apprenant en transcript et
/// réponse de l'IA en sous-titre. Aucune logique métier : tout passe
/// par [ConversationViewModel].
class ConversationScreen extends ConsumerStatefulWidget {
  const ConversationScreen({super.key});

  @override
  ConsumerState<ConversationScreen> createState() => _ConversationScreenState();
}

class _ConversationScreenState extends ConsumerState<ConversationScreen>
    with PracticeScreenLifecycle {
  // Captured while mounted so teardown never touches `ref` during dispose —
  // Riverpod forbids using a widget's `ref` once it is unmounting. The notifier
  // outlives the widget (its provider is not autoDispose), so the reference stays
  // valid.
  ConversationViewModel? _vm;

  /// Cut the mic + hands-free loop when this screen is backgrounded or left,
  /// without ending the session (#222). The "Terminer" button uses [end]/[_endSession].
  @override
  Future<void> stopPractice() async => _vm?.cancel();

  @override
  void initState() {
    super.initState();
    _vm = ref.read(conversationViewModelProvider.notifier);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final params = GoRouterState.of(context).uri.queryParameters;
      final missionId = int.tryParse(params['mission'] ?? '');
      ref
          .read(conversationViewModelProvider.notifier)
          .start(
            mode: params['mode'] ?? kSessionModeFree,
            scenarioId: params['scenario'],
            missionId: missionId,
          );
    });
  }

  Future<void> _endSession() async {
    // Read before end() resets the state — carry the skill so the debrief can chain
    // into "Ma preuve" for a scenario session (#198).
    final state = ref.read(conversationViewModelProvider);
    final sessionId = state.sessionId;
    final scenarioId = state.scenarioId;
    await ref.read(conversationViewModelProvider.notifier).end();
    if (!mounted) return;
    context.go(
      sessionId != null ? Routes.debrief(sessionId, scenarioId: scenarioId) : Routes.home,
    );
  }

  String get _topic {
    final params = GoRouterState.of(context).uri.queryParameters;
    final scenarioId = params['scenario'];
    if (params['mode'] == kSessionModeScenario && scenarioId != null) {
      return scenarioTitle(scenarioId);
    }
    return 'Conversation libre';
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(conversationViewModelProvider);
    final colors = context.colors;

    if (state.quotaExhausted) {
      return const Scaffold(body: SafeArea(child: _QuotaExhausted()));
    }

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            children: [
              _TopBar(
                topic: _topic,
                active: state.isActive,
                onEnd: _endSession,
              ),
              const NetworkBanner(),
              if (ref.watch(demoModeProvider).value ?? false)
                const _DemoBanner(),
              Expanded(child: _OrbZone(state: state)),
              _TranscriptZone(state: state),
              if (state.error != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.md),
                  child: Text(
                    state.error!,
                    key: const Key('conversation_error'),
                    style: AppType.label(colors.accent),
                    textAlign: TextAlign.center,
                  ),
                ),
              const SizedBox(height: AppSpacing.xl),
            ],
          ),
        ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({
    required this.topic,
    required this.active,
    required this.onEnd,
  });

  final String topic;
  final bool active;
  final Future<void> Function() onEnd;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        SessionStatusPill(
          key: const Key('status_pill'),
          topic: topic,
          active: active,
        ),
        const Spacer(),
        IconButton(
          key: const Key('end_button'),
          icon: const Icon(Icons.call_end),
          color: context.colors.textSecondary,
          tooltip: 'Terminer la session',
          onPressed: onEnd,
        ),
      ],
    );
  }
}

/// Orbe central + overline d'état. Tap sur l'orbe (idle) = parler.
class _OrbZone extends ConsumerWidget {
  const _OrbZone({required this.state});

  final ConversationState state;

  static VoiceOrbState _orbStateFor(ConversationStatus status) =>
      switch (status) {
        ConversationStatus.idle => VoiceOrbState.idle,
        ConversationStatus.listening => VoiceOrbState.listening,
        ConversationStatus.thinking => VoiceOrbState.thinking,
        ConversationStatus.speaking => VoiceOrbState.speaking,
      };

  static String _labelFor(ConversationStatus status) => switch (status) {
        ConversationStatus.idle => "touche l'orbe pour parler",
        ConversationStatus.listening => "je t'écoute — touche pour arrêter",
        ConversationStatus.thinking => 'je réfléchis',
        ConversationStatus.speaking => 'je te réponds',
      };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final vm = ref.read(conversationViewModelProvider.notifier);
    final idle = state.status == ConversationStatus.idle;
    // Idle -> start the hands-free loop. Listening -> tap to stop early.
    // Thinking/speaking -> not interruptible by tap (reply in flight).
    final VoidCallback? onTap = !state.isActive
        ? null
        : idle
            ? vm.listenAndRespond
            : state.status == ConversationStatus.listening
                ? vm.stopConversation
                : null;

    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        GestureDetector(
          key: const Key('mic_button'),
          onTap: onTap,
          child: VoiceOrb(state: _orbStateFor(state.status)),
        ),
        const SizedBox(height: AppSpacing.xl),
        OverlineText(_labelFor(state.status)),
      ],
    );
  }
}

/// Dernier échange : la phrase de l'apprenant en Fraunces, la réponse de
/// l'IA en sous-titre discret (elle est déjà lue à voix haute).
class _TranscriptZone extends StatelessWidget {
  const _TranscriptZone({required this.state});

  final ConversationState state;

  ConversationTurn? _lastTurn(String role) {
    for (final turn in state.turns.reversed) {
      if (turn.role == role) return turn;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final listening = state.status == ConversationStatus.listening;
    final lastUser = _lastTurn(kRoleUser);
    // While listening, show the live partial words; otherwise the last final
    // user turn. Live feedback tells the learner the mic is actually hearing.
    final userText = listening
        ? (state.partialTranscript ?? '')
        : (lastUser?.content ?? '');
    final assistantText = _lastTurn(kRoleAssistant)?.content;
    // The gold correction chip appears only after the learner stopped speaking
    // (non-interruption): so, not while listening.
    final correction = listening ? null : lastUser?.correction;
    final colors = context.colors;

    return Column(
      children: [
        if (userText.isNotEmpty)
          TranscriptText(userText, listening: listening),
        if (correction != null)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.md),
            child: _TappableCorrection(correction: correction),
          ),
        if (assistantText != null)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.md),
            child: Text(
              assistantText,
              style: AppType.body(colors.textSecondary),
              textAlign: TextAlign.center,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
            ),
          ),
      ],
    );
  }
}

/// Shown when the backend runs on the fake engine (no DeepSeek key): the app
/// invents replies and cannot correct — say so plainly rather than pretend.
class _DemoBanner extends StatelessWidget {
  const _DemoBanner();

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Container(
      key: const Key('demo_banner'),
      width: double.infinity,
      margin: const EdgeInsets.only(top: AppSpacing.md),
      padding: const EdgeInsets.symmetric(
        vertical: AppSpacing.sm,
        horizontal: AppSpacing.md,
      ),
      decoration: BoxDecoration(
        color: colors.surfaceAlt,
        borderRadius: BorderRadius.circular(AppRadius.chip),
        border: Border.all(color: colors.border, width: AppStroke.hairline),
      ),
      child: Text(
        'Mode démo — réponses simulées, aucune correction. '
        'Configure une clé DeepSeek pour l’expérience réelle.',
        style: AppType.label(colors.textMuted),
        textAlign: TextAlign.center,
      ),
    );
  }
}

/// The gold correction chip, tappable to reveal the grammar rule and
/// alternative phrasings (the "grammar options") in a bottom sheet.
class _TappableCorrection extends StatelessWidget {
  const _TappableCorrection({required this.correction});

  final TurnCorrection correction;

  bool get _hasDetails =>
      correction.rule.isNotEmpty || correction.alternatives.isNotEmpty;

  @override
  Widget build(BuildContext context) {
    final chip = CorrectionChip(
      key: const Key('turn_correction_chip'),
      original: correction.original,
      corrected: correction.correction,
    );
    if (!_hasDetails) return chip;
    return GestureDetector(
      key: const Key('turn_correction_tap'),
      onTap: () => showGrammarSheet(context, correction),
      child: chip,
    );
  }
}

/// Shown when the daily free quota is spent — DESIGN_SPEC §9: a clear, warm
/// message with a way forward, never a hard cut. No upgrade flow exists yet,
/// so the primary action returns home; the copy sets up the future paywall.
class _QuotaExhausted extends StatelessWidget {
  const _QuotaExhausted();

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          key: const Key('quota_exhausted'),
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.hourglass_bottom, size: 40, color: colors.accent),
            const SizedBox(height: AppSpacing.lg),
            Text(
              'Ton temps gratuit du jour est terminé.',
              style: AppType.displayMd(colors.textPrimary),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              'Reviens demain pour continuer à progresser — '
              'ou passe au premium bientôt pour parler sans limite.',
              style: AppType.body(colors.textSecondary),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.xl),
            AppButton.primary(
              key: const Key('quota_home_button'),
              label: "Revenir à l'accueil",
              onPressed: () => context.go(Routes.home),
            ),
          ],
        ),
      ),
    );
  }
}

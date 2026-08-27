import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/providers.dart';
import '../../../core/router/routes.dart';
import '../../../core/ui/app_back_leading.dart';
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
      unawaited(
        ref
            .read(conversationViewModelProvider.notifier)
            .start(
              mode: params['mode'] ?? kSessionModeFree,
              scenarioId: params['scenario'],
              missionId: missionId,
            ),
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
      sessionId != null
          ? Routes.debrief(sessionId, scenarioId: scenarioId)
          : Routes.home,
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

    if (state.sessionConflict) {
      return const Scaffold(body: SafeArea(child: _SessionConflict()));
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
                remainingMinutes: state.remainingMinutes,
                onEnd: _endSession,
              ),
              const NetworkBanner(),
              if (state.quotaWarning) const _QuotaWarning(),
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
    this.remainingMinutes,
  });

  final String topic;
  final bool active;
  final double? remainingMinutes;
  final Future<void> Function() onEnd;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const AppBackLeading(),
        SessionStatusPill(
          key: const Key('status_pill'),
          topic: topic,
          active: active,
        ),
        const Spacer(),
        if (active && remainingMinutes != null)
          Padding(
            padding: const EdgeInsets.only(right: AppSpacing.sm),
            child: Text(
              '${remainingMinutes!.floor()} min',
              key: const Key('quota_remaining'),
              style: AppType.label(context.colors.textSecondary),
            ),
          ),
        if (active)
          AppButton.ghost(
            key: const Key('end_button'),
            label: 'Terminer',
            onPressed: onEnd,
          ),
      ],
    );
  }
}

class _QuotaWarning extends StatelessWidget {
  const _QuotaWarning();

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Text(
        'Plus que 20 % de ton temps gratuit aujourd’hui.',
        key: const Key('quota_warning'),
        style: AppType.label(colors.accent),
        textAlign: TextAlign.center,
      ),
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
    ConversationStatus.idle => 'Parler',
    ConversationStatus.listening => 'Envoyer',
    ConversationStatus.thinking || ConversationStatus.speaking => 'Interrompre',
  };

  /// #329: what a tap DOES right now, not how to perform it (Flutter's
  /// SemanticsHintOverrides convention — "parler", not "touche pour parler").
  /// Null only while the session isn't active — a hint promising an action
  /// that won't happen would mislead a screen-reader user.
  static String? _tapHintFor(ConversationStatus status) => switch (status) {
    ConversationStatus.idle => 'parler',
    ConversationStatus.listening => 'envoyer',
    ConversationStatus.thinking || ConversationStatus.speaking => 'interrompre',
  };

  /// #329: the accessibility label must stay accurate even before a session
  /// is active (no sessionId yet — the brief window while start() is still
  /// resolving). [_labelFor]'s idle text is an instruction to tap; announcing
  /// that on a node [enabled] simultaneously marks non-interactive would
  /// mislead a screen-reader user.
  static String _semanticsLabelFor(ConversationState state) =>
      state.isActive ? _labelFor(state.status) : 'session en préparation';

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final vm = ref.read(conversationViewModelProvider.notifier);
    final idle = state.status == ConversationStatus.idle;
    // Idle -> listen. Listening -> send what was heard. Thinking/speaking ->
    // interrupt and start a new turn.
    final VoidCallback? onTap = !state.isActive
        ? null
        : idle
        ? vm.listenAndRespond
        : state.status == ConversationStatus.listening
        ? vm.finishCurrentUtterance
        : vm.listenAndRespond;

    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Semantics(
          button: true,
          enabled: onTap != null,
          label: _semanticsLabelFor(state),
          onTapHint: state.isActive ? _tapHintFor(state.status) : null,
          child: GestureDetector(
            key: const Key('mic_button'),
            onTap: onTap,
            child: VoiceOrb(state: _orbStateFor(state.status)),
          ),
        ),
        const SizedBox(height: AppSpacing.xl),
        // Excluded from the semantics tree: it repeats the orb's own
        // Semantics.label verbatim (#329 reuses this exact text on purpose),
        // so without this a screen reader would announce the same phrase
        // twice in a row while swiping through.
        ExcludeSemantics(child: OverlineText(_labelFor(state.status))),
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
        if (userText.isNotEmpty) TranscriptText(userText, listening: listening),
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

/// Shown when the backend runs on the fake engine: the app invents replies
/// and cannot correct — say so plainly rather than pretend.
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
        'Mode démo — réponses simulées, aucune correction.',
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

/// Shown when a target-less start hits 409: the learner chooses to resume
/// the open session or end it and start over. No orb until they pick.
class _SessionConflict extends ConsumerWidget {
  const _SessionConflict();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = context.colors;
    final vm = ref.read(conversationViewModelProvider.notifier);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          key: const Key('session_conflict'),
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.forum_outlined, size: 40, color: colors.accent),
            const SizedBox(height: AppSpacing.lg),
            Text(
              'Une conversation est déjà en cours.',
              style: AppType.displayMd(colors.textPrimary),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.xl),
            AppButton.primary(
              key: const Key('resume_session'),
              label: 'Reprendre',
              onPressed: vm.resumePending,
            ),
            const SizedBox(height: AppSpacing.md),
            AppButton.outlined(
              key: const Key('replace_session'),
              label: 'Terminer et recommencer',
              onPressed: vm.replacePending,
            ),
          ],
        ),
      ),
    );
  }
}

/// Shown when the daily free quota is spent. No payment yet (#503): honest
/// quota-only page, come back tomorrow.
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
              'Ton temps du jour est utilisé.',
              style: AppType.displayMd(colors.textPrimary),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              'Le parcours gratuit, c’est 10 minutes par jour. '
              'Pas d’abonnement pour l’instant. Reviens demain.',
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

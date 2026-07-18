import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/models/scenarios.dart';
import '../../../data/models/session_modes.dart';
import '../../../design_system/atoms/overline_text.dart';
import '../../../design_system/molecules/transcript_text.dart';
import '../../../design_system/organisms/voice_orb.dart';
import '../view_model/conversation_state.dart';
import '../view_model/conversation_view_model.dart';
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

class _ConversationScreenState extends ConsumerState<ConversationScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final params = GoRouterState.of(context).uri.queryParameters;
      ref
          .read(conversationViewModelProvider.notifier)
          .start(
            mode: params['mode'] ?? kSessionModeFree,
            scenarioId: params['scenario'],
          );
    });
  }

  Future<void> _endSession() async {
    final sessionId = ref.read(conversationViewModelProvider).sessionId;
    await ref.read(conversationViewModelProvider.notifier).end();
    if (!mounted) return;
    context.go(sessionId != null ? Routes.debrief(sessionId) : Routes.home);
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
        ConversationStatus.listening => "je t'écoute",
        ConversationStatus.thinking => 'je réfléchis',
        ConversationStatus.speaking => 'je te réponds',
      };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final idle = state.status == ConversationStatus.idle;
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        GestureDetector(
          key: const Key('mic_button'),
          onTap: idle && state.isActive
              ? () => ref
                    .read(conversationViewModelProvider.notifier)
                    .listenAndRespond()
              : null,
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

  String? _lastContent(String role) {
    for (final turn in state.turns.reversed) {
      if (turn.role == role) return turn.content;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final userText = _lastContent(kRoleUser);
    final assistantText = _lastContent(kRoleAssistant);
    final colors = context.colors;

    return Column(
      children: [
        if (userText != null)
          TranscriptText(
            userText,
            listening: state.status == ConversationStatus.listening,
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

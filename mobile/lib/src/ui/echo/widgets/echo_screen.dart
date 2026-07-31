import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/models/echo.dart';
import '../../../data/models/pronunciation_scoring.dart';
import '../../../design_system/atoms/app_button.dart';
import '../../../design_system/atoms/overline_text.dart';
import '../../../design_system/organisms/voice_orb.dart';
import '../view_model/echo_state.dart';
import '../view_model/echo_view_model.dart';

/// Mode Écho (self-monitoring shadowing): the learner hears a model phrase,
/// reads it aloud while recording, then replays their own voice against the
/// model (A/B) and sees which words did not come through, with coaching.
///
/// Requires server-side voice (TTS to speak the model, STT to score). When the
/// backend has neither, the screen says so honestly instead of dead-ending on a
/// 404.
class EchoScreen extends ConsumerStatefulWidget {
  const EchoScreen({super.key});

  @override
  ConsumerState<EchoScreen> createState() => _EchoScreenState();
}

class _EchoScreenState extends ConsumerState<EchoScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Only load a phrase if the server can actually run shadowing.
      final tts = await ref.read(serverTtsProvider.future);
      final stt = await ref.read(serverSttProvider.future);
      if (!mounted) return;
      if (tts && stt) {
        await ref.read(echoViewModelProvider.notifier).loadPhrase();
      } else {
        ref.read(echoViewModelProvider.notifier).markUnavailable();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(echoViewModelProvider);
    final colors = context.colors;

    return Scaffold(
      appBar: AppBar(title: const Text('Mode Écho')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: state.unavailable
              ? const _Unavailable()
              : _RoundView(state: state),
        ),
      ),
      backgroundColor: colors.surface,
    );
  }
}

class _Unavailable extends StatelessWidget {
  const _Unavailable();

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.cloud_off, size: 48, color: colors.textMuted),
          const SizedBox(height: AppSpacing.lg),
          Text(
            'Le Mode Écho nécessite la voix du serveur '
            '(synthèse et reconnaissance). Elle n’est pas activée ici.',
            key: const Key('echo_unavailable'),
            textAlign: TextAlign.center,
            style: AppType.body(colors.textSecondary),
          ),
        ],
      ),
    );
  }
}

class _RoundView extends ConsumerWidget {
  const _RoundView({required this.state});

  final EchoState state;

  static VoiceOrbState _orbFor(EchoPhase phase) => switch (phase) {
        EchoPhase.idle => VoiceOrbState.idle,
        EchoPhase.playingModel => VoiceOrbState.speaking,
        EchoPhase.recording => VoiceOrbState.listening,
        EchoPhase.scoring => VoiceOrbState.thinking,
        EchoPhase.reviewing => VoiceOrbState.idle,
      };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final vm = ref.read(echoViewModelProvider.notifier);
    final colors = context.colors;

    if (!state.hasPhrase) {
      return const Center(child: CircularProgressIndicator());
    }

    // Idle -> tap the orb to record; recording -> tap to stop & score.
    final VoidCallback? orbTap = switch (state.phase) {
      EchoPhase.idle || EchoPhase.reviewing => vm.record,
      EchoPhase.recording => vm.stopAndScore,
      _ => null,
    };

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OverlineText('round ${state.round} / $kEchoTotalRounds'),
        const SizedBox(height: AppSpacing.lg),
        _PhraseText(phrase: state.phrase!, result: state.result),
        if (state.phrase!.tip.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(state.phrase!.tip, style: AppType.label(colors.textMuted)),
        ],
        const Spacer(),
        Center(
          child: GestureDetector(
            key: const Key('echo_orb'),
            onTap: orbTap,
            child: VoiceOrb(state: _orbFor(state.phase)),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        Center(child: OverlineText(_labelFor(state.phase))),
        const Spacer(),
        if (state.error != null) ...[
          Text(
            state.error!,
            key: const Key('echo_error'),
            style: AppType.label(colors.accent),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: AppSpacing.md),
        ],
        // The feedback (coaching + per-phoneme detail) can be tall on small
        // screens; let it scroll instead of overflowing the fixed column.
        if (state.result != null)
          Flexible(
            child: SingleChildScrollView(child: _Feedback(state: state)),
          ),
        _Controls(state: state),
      ],
    );
  }

  static String _labelFor(EchoPhase phase) => switch (phase) {
        EchoPhase.idle => 'touche pour t’enregistrer',
        EchoPhase.playingModel => 'écoute le modèle',
        EchoPhase.recording => 'je t’écoute — touche pour arrêter',
        // Scoring runs STT + the GOP acoustic model (~2-3 s on CPU); tell the
        // learner their sounds are being analyzed so the wait is understood.
        EchoPhase.scoring => 'analyse de tes sons…',
        EchoPhase.reviewing => 'compare ta voix au modèle',
      };
}

/// The target phrase, with missed words highlighted once an attempt is scored.
class _PhraseText extends StatelessWidget {
  const _PhraseText({required this.phrase, this.result});

  final ShadowingPhrase phrase;
  final AttemptResult? result;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;

    // Color each word by its pronunciation-clarity score (#111), matching the
    // scored words to the target by position. A word with no reliable score
    // stays uncolored — an honest display, not a guessed one.
    Color? colorFor(int index) {
      final words = result?.words;
      if (words == null || index >= words.length) return null;
      final w = words[index];
      if (!w.hasReliableScore) return null;
      final score = w.score!;
      if (score >= kPronunciationStrongThreshold) return colors.positive;
      if (score >= kPronunciationReviewThreshold) return colors.correction;
      return colors.accent; // needs practice
    }

    List<InlineSpan> spans() {
      final targetWords = phrase.text.split(RegExp(r'\s+'));
      final out = <InlineSpan>[];
      for (var i = 0; i < targetWords.length; i++) {
        final color = result == null ? null : colorFor(i);
        out.add(TextSpan(
          text: targetWords[i],
          style: color == null
              ? null
              : TextStyle(color: color, fontWeight: FontWeight.w600),
        ));
        out.add(const TextSpan(text: ' '));
      }
      return out;
    }

    return Text.rich(
      TextSpan(children: spans()),
      key: const Key('echo_phrase'),
      textAlign: TextAlign.center,
      style: AppType.displayMd(colors.textPrimary),
    );
  }
}

/// A/B replay + coaching, shown after an attempt is scored.
class _Feedback extends ConsumerWidget {
  const _Feedback({required this.state});

  final EchoState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final vm = ref.read(echoViewModelProvider.notifier);
    final colors = context.colors;
    final result = state.result!;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: AppButton.outlined(
                label: 'Modèle',
                icon: Icons.volume_up,
                onPressed: vm.playModel,
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: AppButton.outlined(
                label: 'Ma voix',
                icon: Icons.record_voice_over,
                onPressed: state.canReplayMine ? vm.playMine : null,
              ),
            ),
          ],
        ),
        if (state.coaching != null && state.coaching!.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: colors.correctionBg,
              borderRadius: BorderRadius.circular(AppRadius.card),
              border: Border.all(color: colors.correctionBorder),
            ),
            child: Text(
              state.coaching!,
              key: const Key('echo_coaching'),
              style: AppType.body(colors.textPrimary),
            ),
          ),
        ] else if (state.coachingLoading) ...[
          // The score is already shown; the coaching tip is still loading.
          const SizedBox(height: AppSpacing.md),
          Row(
            key: const Key('echo_coaching_loading'),
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2, color: colors.textMuted),
              ),
              const SizedBox(width: AppSpacing.sm),
              Text('conseil en préparation…', style: AppType.label(colors.textMuted)),
            ],
          ),
        ] else if (result.isPerfect) ...[
          const SizedBox(height: AppSpacing.md),
          Text(
            'Parfait — tous les mots sont passés !',
            key: const Key('echo_perfect'),
            style: AppType.body(colors.positive),
            textAlign: TextAlign.center,
          ),
        ],
        if (result.phonemes.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          _PhonemeDetail(phonemes: result.phonemes),
        ],
        const SizedBox(height: AppSpacing.md),
      ],
    );
  }
}

/// Per-phoneme pronunciation detail (#111 step 2): one colored chip per expected
/// phoneme, so the learner sees exactly which sound (e.g. /θ/) needs work — finer
/// than the word-level highlighting. Only shown when the backend's GOP engine is
/// on; empty otherwise.
///
/// Honest by design: the GOP score is a raw acoustic measure, not calibrated on
/// French-speaker voices, so we label it "à titre indicatif" rather than present
/// it as a verdict (tracked debt from the pronunciation microservice).
class _PhonemeDetail extends StatelessWidget {
  const _PhonemeDetail({required this.phonemes});

  final List<EchoPhonemeScore> phonemes;

  Color _colorFor(EchoPhonemeScore p, AppSemanticColors colors) {
    if (p.isStrong) return colors.positive;
    if (!p.needsPractice) return colors.correction; // review band
    return colors.accent; // needs practice
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Column(
      key: const Key('echo_phonemes'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        OverlineText('Sons', color: colors.textSecondary),
        const SizedBox(height: AppSpacing.sm),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            for (final p in phonemes)
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.xs,
                ),
                decoration: BoxDecoration(
                  color: _colorFor(p, colors).withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(AppRadius.pill),
                  border: Border.all(color: _colorFor(p, colors)),
                ),
                child: Text(
                  '/${p.phoneme}/',
                  style: AppType.body(_colorFor(p, colors)),
                ),
              ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          'À titre indicatif : score acoustique, pas encore calibré sur des voix francophones.',
          key: const Key('echo_phonemes_uncertainty'),
          style: AppType.label(colors.textSecondary),
        ),
      ],
    );
  }
}

class _Controls extends ConsumerWidget {
  const _Controls({required this.state});

  final EchoState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final vm = ref.read(echoViewModelProvider.notifier);
    // Before an attempt: let them (re)hear the model. After: advance rounds.
    if (state.result == null) {
      return AppButton.primary(
        label: 'Écouter le modèle',
        icon: Icons.play_arrow,
        onPressed: state.phase == EchoPhase.idle ? vm.playModel : null,
        fullWidth: true,
      );
    }
    return AppButton.primary(
      label: state.isLastRound ? 'Terminer' : 'Phrase suivante',
      icon: Icons.arrow_forward,
      onPressed: state.isLastRound ? null : vm.nextRound,
      fullWidth: true,
    );
  }
}

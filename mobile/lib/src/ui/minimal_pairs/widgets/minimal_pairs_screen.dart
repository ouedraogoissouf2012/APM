import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/providers.dart';
import '../../../core/ui/app_back_leading.dart';
import '../../../data/models/echo.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/ui/practice_screen_lifecycle.dart';
import '../../../design_system/atoms/app_button.dart';
import '../../../design_system/atoms/overline_text.dart';
import '../../../design_system/organisms/voice_orb.dart';
import '../view_model/minimal_pairs_state.dart';
import '../view_model/minimal_pairs_view_model.dart';

/// Minimal-pairs drill (#112): Ava says one word of a confusable pair
/// (ship/sheep); the learner guesses which they heard (discrimination), then
/// says it themselves (production, scored + confusion detected). Requires server
/// voice (TTS to speak the word, STT to score).
class MinimalPairsScreen extends ConsumerStatefulWidget {
  const MinimalPairsScreen({super.key});

  @override
  ConsumerState<MinimalPairsScreen> createState() => _MinimalPairsScreenState();
}

class _MinimalPairsScreenState extends ConsumerState<MinimalPairsScreen>
    with PracticeScreenLifecycle {
  // Captured while mounted; teardown must not touch `ref` during dispose.
  MinimalPairsViewModel? _vm;

  /// Discard an in-progress recording and free the mic when this screen is
  /// backgrounded or left (#222).
  @override
  Future<void> stopPractice() async => _vm?.cancel();

  @override
  void initState() {
    super.initState();
    _vm = ref.read(minimalPairsViewModelProvider.notifier);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final tts = await ref.read(serverTtsProvider.future);
      final stt = await ref.read(serverSttProvider.future);
      if (!mounted) return;
      if (tts && stt) {
        final vm = ref.read(minimalPairsViewModelProvider.notifier);
        await vm.loadPair();
        if (mounted) await vm.playWord();
      } else {
        ref.read(minimalPairsViewModelProvider.notifier).markUnavailable();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(minimalPairsViewModelProvider);
    final colors = context.colors;

    return Scaffold(
      appBar: AppBar(
        leading: const AppBackLeading(),
        title: const Text('Paires minimales'),
      ),
      backgroundColor: colors.surface,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: state.unavailable
              ? const _Unavailable()
              : !state.hasPair
              ? const Center(child: CircularProgressIndicator())
              : _RoundView(state: state),
        ),
      ),
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
            'Les paires minimales ne sont pas disponibles pour le moment.',
            key: const Key('pairs_unavailable'),
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

  final MinimalPairsState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final vm = ref.read(minimalPairsViewModelProvider.notifier);
    final colors = context.colors;
    final pair = state.pair!;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OverlineText('round ${state.round} / $kMinimalPairsTotalRounds'),
        const SizedBox(height: AppSpacing.sm),
        Center(child: Text(pair.sound, style: AppType.label(colors.textMuted))),
        const SizedBox(height: AppSpacing.lg),
        const Spacer(),
        Center(
          child: GestureDetector(
            onTap: state.phase == PairPhase.guessing ||
                    state.phase == PairPhase.playing
                ? vm.playWord
                : null,
            child: VoiceOrb(state: _orbFor(state.phase)),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        Center(child: OverlineText(_labelFor(state.phase))),
        const Spacer(),
        if (state.error != null) ...[
          Text(
            state.error!,
            key: const Key('pairs_error'),
            style: AppType.label(colors.accent),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: AppSpacing.md),
        ],
        _Body(state: state),
      ],
    );
  }

  static VoiceOrbState _orbFor(PairPhase phase) => switch (phase) {
    PairPhase.playing => VoiceOrbState.speaking,
    PairPhase.recording => VoiceOrbState.listening,
    PairPhase.scoring => VoiceOrbState.thinking,
    _ => VoiceOrbState.idle,
  };

  static String _labelFor(PairPhase phase) => switch (phase) {
    PairPhase.playing => 'écoute Ava',
    PairPhase.guessing => 'quel mot as-tu entendu ?',
    PairPhase.guessed => 'à ton tour de le dire',
    PairPhase.recording => 'je t’écoute — touche pour arrêter',
    PairPhase.scoring => 'analyse…',
    PairPhase.reviewing => 'résultat',
    PairPhase.idle => '',
  };
}

/// The interactive body: choice buttons during discrimination, the record orb
/// + result during production.
class _Body extends ConsumerWidget {
  const _Body({required this.state});

  final MinimalPairsState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final vm = ref.read(minimalPairsViewModelProvider.notifier);
    final pair = state.pair!;

    switch (state.phase) {
      case PairPhase.guessing:
      case PairPhase.playing:
        return Column(
          children: [
            AppButton.ghost(
              label: 'Réécouter',
              icon: Icons.volume_up,
              onPressed: vm.playWord,
            ),
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: [
                Expanded(
                  child: _ChoiceButton(
                    word: pair.wordA,
                    onTap: vm.guess,
                    primary: true,
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: _ChoiceButton(
                    word: pair.wordB,
                    onTap: vm.guess,
                    primary: true,
                  ),
                ),
              ],
            ),
          ],
        );
      case PairPhase.guessed:
        return _AfterGuess(state: state);
      case PairPhase.recording:
        return AppButton.primary(
          label: 'Terminer',
          icon: Icons.stop,
          onPressed: vm.stopAndScore,
          fullWidth: true,
        );
      case PairPhase.scoring:
        return const SizedBox.shrink();
      case PairPhase.reviewing:
        return _Result(state: state);
      case PairPhase.idle:
        return const SizedBox.shrink();
    }
  }
}

class _ChoiceButton extends StatelessWidget {
  const _ChoiceButton({
    required this.word,
    required this.onTap,
    this.primary = false,
  });

  final String word;
  final void Function(String) onTap;
  final bool primary;

  @override
  Widget build(BuildContext context) {
    if (primary) {
      return AppButton.primary(
        key: Key('choice_$word'),
        label: word,
        onPressed: () => onTap(word),
      );
    }
    return AppButton.outlined(
      key: Key('choice_$word'),
      label: word,
      onPressed: () => onTap(word),
    );
  }
}

/// Shows whether the discrimination guess was right, then a record button to
/// produce the word.
class _AfterGuess extends ConsumerWidget {
  const _AfterGuess({required this.state});

  final MinimalPairsState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final vm = ref.read(minimalPairsViewModelProvider.notifier);
    final colors = context.colors;
    final correct = state.guessedCorrectly;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          correct
              ? 'Bravo — c’était bien « ${state.spokenWord} ».'
              : 'C’était « ${state.spokenWord} », pas « ${state.guess} ».',
          key: const Key('pairs_guess_feedback'),
          textAlign: TextAlign.center,
          style: AppType.body(correct ? colors.positive : colors.accent),
        ),
        const SizedBox(height: AppSpacing.md),
        AppButton.primary(
          label: 'Prononce « ${state.spokenWord} »',
          icon: Icons.mic,
          onPressed: vm.record,
          fullWidth: true,
        ),
      ],
    );
  }
}

/// Production result: said the target, or the other word of the pair, + coaching.
class _Result extends ConsumerWidget {
  const _Result({required this.state});

  final MinimalPairsState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final vm = ref.read(minimalPairsViewModelProvider.notifier);
    final colors = context.colors;
    final attempt = state.attempt!;

    final String verdict;
    final Color verdictColor;
    if (attempt.saidTarget) {
      verdict =
          'Bien prononcé — « ${state.spokenWord} » est passé clairement !';
      verdictColor = colors.positive;
    } else if (attempt.saidOther) {
      final pair = state.pair!;
      final other = state.spokenWord == pair.wordA ? pair.wordB : pair.wordA;
      verdict = 'On a entendu « $other ». Vise « ${state.spokenWord} ».';
      verdictColor = colors.accent;
    } else {
      verdict = 'Pas tout à fait — réessaie « ${state.spokenWord} ».';
      verdictColor = colors.accent;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          verdict,
          key: const Key('pairs_verdict'),
          textAlign: TextAlign.center,
          style: AppType.body(verdictColor),
        ),
        if (isLearnerFacingTip(attempt.coaching)) ...[
          const SizedBox(height: AppSpacing.md),
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: colors.correctionBg,
              borderRadius: BorderRadius.circular(AppRadius.card),
              border: Border.all(color: colors.correctionBorder),
            ),
            child: Text(
              attempt.coaching,
              key: const Key('pairs_coaching'),
              style: AppType.body(colors.textPrimary),
            ),
          ),
        ],
        const SizedBox(height: AppSpacing.md),
        Row(
          children: [
            Expanded(
              child: AppButton.outlined(
                label: 'Ma voix',
                icon: Icons.record_voice_over,
                onPressed: state.myRecording != null ? vm.playMine : null,
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: AppButton.primary(
                label: state.isLastRound ? 'Terminer' : 'Paire suivante',
                icon: Icons.arrow_forward,
                // Gated on `reviewing` too (#350), not just `isLastRound`:
                // a defensive backstop matching echo_screen.dart's
                // "Phrase suivante" gate — the VM-level `_busy` guard is
                // what actually prevents the soft-lock, but this keeps the
                // button's enabled-ness honest with the same rule the VM
                // enforces, instead of relying solely on this widget only
                // ever being built while `state.phase == reviewing`.
                onPressed:
                    state.isLastRound || state.phase != PairPhase.reviewing
                    ? null
                    : vm.nextRound,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

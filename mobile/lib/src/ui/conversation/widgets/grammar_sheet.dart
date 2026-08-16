import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/models/turn_correction.dart';
import '../../../design_system/atoms/overline_text.dart';
import '../reformulation.dart';
import '../view_model/conversation_providers.dart';

/// Opens the grammar detail sheet for a correction: the rule (the "why") and
/// alternative phrasings (the "grammar options" the learner asked for).
Future<void> showGrammarSheet(
  BuildContext context,
  TurnCorrection correction,
) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: context.colors.surface,
    showDragHandle: true,
    builder: (_) => _GrammarSheet(correction: correction),
  );
}

class _GrammarSheet extends StatelessWidget {
  const _GrammarSheet({required this.correction});

  final TurnCorrection correction;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final gold = colors.correction;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.xl,
          0,
          AppSpacing.xl,
          AppSpacing.xl,
        ),
        child: Column(
          key: const Key('grammar_sheet'),
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            OverlineText('ta correction', color: gold),
            const SizedBox(height: AppSpacing.md),
            Text.rich(
              TextSpan(
                style: AppType.displayMd(colors.textPrimary),
                children: [
                  TextSpan(
                    text: correction.original,
                    style: TextStyle(
                      color: colors.textMuted,
                      decoration: TextDecoration.lineThrough,
                    ),
                  ),
                  const TextSpan(text: '  →  '),
                  TextSpan(text: correction.correction, style: TextStyle(color: gold)),
                ],
              ),
            ),
            if (correction.rule.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.lg),
              Text(correction.rule, style: AppType.body(colors.textSecondary)),
            ],
            if (correction.alternatives.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.xl),
              OverlineText('tu peux aussi dire', color: colors.textMuted),
              const SizedBox(height: AppSpacing.sm),
              for (final alt in correction.alternatives)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.xs),
                  child: Text(
                    '· $alt',
                    style: AppType.body(colors.textPrimary),
                  ),
                ),
            ],
            const SizedBox(height: AppSpacing.xl),
            // Reformulation step (#200): say the corrected sentence RIGHT NOW and
            // get immediate feedback, instead of only reading the fix.
            _ReformulationTile(target: correction.correction),
          ],
        ),
      ),
    );
  }
}

enum _ReformStatus { idle, recording, checking, done }

/// "Redis-le" — records the learner re-saying the corrected sentence, transcribes
/// it, and tells them whether they nailed it. Reuses the shared recorder + the
/// server transcription; state is local to this tile.
class _ReformulationTile extends ConsumerStatefulWidget {
  const _ReformulationTile({required this.target});

  final String target;

  @override
  ConsumerState<_ReformulationTile> createState() => _ReformulationTileState();
}

class _ReformulationTileState extends ConsumerState<_ReformulationTile> {
  _ReformStatus _status = _ReformStatus.idle;
  bool? _matched; // null = couldn't verify (mic/STT failed or silence)
  String _heard = '';
  // Cached in initState: a lazy `late final = ref.read(...)` first runs in
  // dispose() if the learner never tapped record — and `ref` is already
  // unmounted then (CI: conversation_screen_test opens/closes the sheet).
  late final _recorder;

  @override
  void initState() {
    super.initState();
    _recorder = ref.read(audioRecordingProvider);
  }

  @override
  void dispose() {
    _recorder.cancel();
    super.dispose();
  }

  Future<void> _onTap() async {
    if (_status == _ReformStatus.recording) {
      await _stopAndCheck();
    } else if (_status != _ReformStatus.checking) {
      await _startRecording();
    }
  }

  Future<void> _startRecording() async {
    final started = await _recorder.start();
    if (!mounted) {
      // #425: start() succeeded after dismiss — drop the hot mic.
      if (started) await _recorder.cancel();
      return;
    }
    if (!started) {
      setState(() {
        _status = _ReformStatus.done;
        _matched = null;
        _heard = '';
      });
      return;
    }
    setState(() => _status = _ReformStatus.recording);
  }

  Future<void> _stopAndCheck() async {
    setState(() => _status = _ReformStatus.checking);
    final bytes = await _recorder.stop();
    String heard = '';
    try {
      if (bytes != null && bytes.isNotEmpty) {
        heard = (await ref.read(conversationRepositoryProvider).transcribe(bytes)).trim();
      }
    } catch (_) {
      heard = '';
    }
    if (!mounted) return;
    setState(() {
      _heard = heard;
      _matched = heard.isEmpty ? null : reformulationMatched(widget.target, heard);
      _status = _ReformStatus.done;
    });
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final label = switch (_status) {
      _ReformStatus.recording => "J'ai fini",
      _ReformStatus.checking => 'Je vérifie…',
      _ => 'Redis-le',
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            key: const Key('reformulation_button'),
            icon: Icon(_status == _ReformStatus.recording ? Icons.stop : Icons.mic),
            label: Text(label),
            onPressed: _status == _ReformStatus.checking ? null : _onTap,
          ),
        ),
        if (_status == _ReformStatus.done) ...[
          const SizedBox(height: AppSpacing.md),
          if (_matched == true)
            Text(
              "C'est ça ! 👏",
              key: const Key('reformulation_ok'),
              style: AppType.body(colors.positive),
            )
          else if (_matched == false)
            Text(
              'Presque — j\'ai entendu : « $_heard ». Réessaie.',
              key: const Key('reformulation_retry'),
              style: AppType.body(colors.textSecondary),
            )
          else
            Text(
              "Je n'ai pas pu t'entendre — réessaie.",
              key: const Key('reformulation_unheard'),
              style: AppType.body(colors.textSecondary),
            ),
        ],
      ],
    );
  }
}

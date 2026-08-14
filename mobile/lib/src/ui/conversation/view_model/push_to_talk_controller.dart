import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/observability/providers.dart';
import '../../../core/observability/ref_report_error.dart';
import 'conversation_host.dart';
import 'conversation_providers.dart';
import 'conversation_state.dart';
import 'reply_playback.dart';

/// Push-to-talk input (server STT / Whisper via Groq): tap to record, tap again
/// to stop → transcribe server-side → respond (#121).
///
/// Extracted from ConversationViewModel. Unlike the hands-free loop, this is a
/// single recording per response, so accurate transcription gets a clean full
/// take. It owns its `_recording` flag and reuses [ReplyPlayback] for the reply —
/// no shared concurrency flag with the loop.
class PushToTalkController {
  PushToTalkController(this._ref, this._host, this._playback);

  final Ref _ref;
  final ConversationHost _host;
  final ReplyPlayback _playback;

  bool _recording = false;
  // The session whose take has already been captured for the audible before/after
  // (#199) — so we keep ONE representative take per scenario session, not one per
  // utterance.
  int? _capturedForSession;

  /// True while recording the learner's utterance, so the view-model routes a
  /// stop tap here and cancels the recording on end().
  bool get isRecording => _recording;

  /// Starts recording the learner's voice.
  Future<void> startRecording() async {
    final started = await _ref.read(audioRecordingProvider).start();
    if (!_host.mounted) return;
    if (!started) {
      _host.state = _host.state.copyWith(error: 'Microphone is not available');
      return;
    }
    _recording = true;
    _host.state = _host.state.copyWith(
      status: ConversationStatus.listening,
      clearError: true,
      clearPartial: true,
    );
  }

  /// Stops recording, transcribes the audio server-side, then responds.
  Future<void> stopAndRespond() async {
    _recording = false;
    final sessionId = _host.state.sessionId;
    final bytes = await _ref.read(audioRecordingProvider).stop();
    if (!_host.mounted || sessionId == null) return;
    if (bytes == null || bytes.isEmpty) {
      _host.state = _host.state.copyWith(status: ConversationStatus.idle);
      return;
    }
    // Audible before/after (#199): keep the FIRST take of each scenario session
    // on-device, keyed by skill, so ProofScreen can play the learner's before vs
    // after. Best-effort — a store failure must never break the turn.
    final skill = _host.state.scenarioId;
    if (skill != null && _capturedForSession != sessionId) {
      _capturedForSession = sessionId;
      try {
        await _ref.read(voiceTakeStoreProvider).saveTake(skill, bytes);
      } catch (e, stack) {
        // Best-effort: never let a capture failure break the conversation
        // turn — but (#236) don't let it vanish silently either, since a
        // recurring failure here (e.g. the secure-storage-backed encryption
        // key becoming unreadable, #226) would otherwise quietly break the
        // audible before/after for every skill without anyone noticing.
        _ref.read(crashReporterProvider).captureError(
              e,
              stack,
              context: 'PushToTalkController.stopAndRespond: voice take capture failed',
              data: {'skill': skill},
            );
      }
    }
    _host.state = _host.state.copyWith(
      status: ConversationStatus.thinking,
      clearPartial: true,
    );
    final String heard;
    try {
      heard = (await _ref.read(conversationRepositoryProvider).transcribe(bytes)).trim();
    } catch (e, s) {
      // #403: a network failure is expected (the learner sees the offline
      // message elsewhere) and stays quiet; anything else here (a backend
      // 5xx, a transcription-service outage) must not vanish silently — it
      // would otherwise be wrongly blamed on the learner's pronunciation.
      final offline = e is ApiException && (e.statusCode == 0 || e.code == 'network');
      if (!offline) {
        _ref.reportError(e, s, context: 'PushToTalkController.stopAndRespond: transcribe failed');
      }
      if (_host.mounted) {
        _host.state = _host.state.copyWith(
          status: ConversationStatus.idle,
          error: 'Could not understand you — try again',
        );
      }
      return;
    }
    if (!_host.mounted) return;
    if (heard.isEmpty) {
      _host.state = _host.state.copyWith(status: ConversationStatus.idle);
      return;
    }
    _host.state = _host.state.copyWith(
      turns: [..._host.state.turns, ConversationTurn(kRoleUser, heard)],
      status: ConversationStatus.thinking,
    );
    // Single response: live as long as the notifier is mounted.
    try {
      await _playback.streamReplyAndSpeak(sessionId, heard, isLive: () => _host.mounted);
    } finally {
      if (_host.mounted &&
          _host.state.sessionId != null &&
          _host.state.status != ConversationStatus.idle) {
        _host.state = _host.state.copyWith(status: ConversationStatus.idle);
      }
    }
  }

  /// Cancels an in-flight recording (used by end()).
  Future<void> cancel() async {
    if (!_recording) return;
    _recording = false;
    await _ref.read(audioRecordingProvider).cancel();
  }
}

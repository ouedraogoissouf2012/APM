import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'conversation_host.dart';
import 'conversation_providers.dart';
import 'conversation_state.dart';
import 'reply_playback.dart';
import 'speech_error_message.dart';

/// The hands-free conversation loop (device STT): listen → send → speak → listen…
/// (#121). One tap begins it; it continues automatically until the learner falls
/// silent, an error occurs, or it is explicitly stopped.
///
/// Extracted from ConversationViewModel. It owns the two concurrency flags the
/// loop needs — the intent flag [_conversing] and the re-entrancy guard
/// [_loopRunning] — and the [isActive] predicate every step checks after an
/// await. Reuses [ReplyPlayback] for the reply, passing its own liveness.
class TurnLoopController {
  TurnLoopController(this._ref, this._host, this._playback);

  final Ref _ref;
  final ConversationHost _host;
  final ReplyPlayback _playback;

  /// Intent flag: true while the learner wants the loop to continue. Cleared by
  /// [stop] to end the loop after the in-flight turn resolves.
  bool _conversing = false;

  /// Re-entrancy guard held for the WHOLE lifetime of [run], released only in its
  /// `finally`. [_conversing] is insufficient alone: [stop] clears it while its
  /// own `stopListening()` is still pending, so a fast stop→re-tap could start a
  /// second loop before the first unwinds — two recognizers, the "already
  /// started" crash. This guard makes a concurrent loop impossible by construction.
  bool _loopRunning = false;

  /// The loop and every turn step are "live" only while wanted and mounted. This
  /// single predicate replaces the checks duplicated after each await, so a step
  /// can never mutate state on behalf of a loop already stopped or disposed.
  bool get isActive => _conversing && _host.mounted;

  /// Runs the hands-free loop until silence, error, or [stop].
  Future<void> run() async {
    if (_loopRunning) return; // a prior loop is still unwinding
    _loopRunning = true;
    _conversing = true;
    try {
      while (isActive && await _runOneTurn()) {}
    } finally {
      _conversing = false;
      _loopRunning = false;
      // Settle back to idle only if a session is still live: end() may have reset
      // the state entirely, and the reply may have set an error we must not
      // clobber. Guarding on an active, non-error session keeps this a no-op then.
      if (_host.mounted &&
          _host.state.sessionId != null &&
          _host.state.status != ConversationStatus.idle) {
        _host.state = _host.state.copyWith(status: ConversationStatus.idle);
      }
    }
  }

  /// Signals the loop to stop after the in-flight turn resolves.
  void stop() {
    _conversing = false;
  }

  /// One listen → respond → speak turn. Returns whether the loop should carry on
  /// (learner spoke and got a reply) or stop (silence, error, or stopped). Each
  /// phase is guarded by [isActive]: a turn resolving after the loop was stopped
  /// simply bails without touching state.
  Future<bool> _runOneTurn() async {
    final sessionId = _host.state.sessionId;
    if (sessionId == null) return false;

    final heard = await _listen();
    if (!isActive) return false;
    if (heard.isEmpty) {
      _surfaceListenError(); // no-op on plain silence, message on failure
      return false;
    }
    _host.state = _host.state.copyWith(
      turns: [..._host.state.turns, ConversationTurn(kRoleUser, heard)],
      status: ConversationStatus.thinking,
    );
    return _playback.streamReplyAndSpeak(sessionId, heard, isLive: () => isActive);
  }

  /// Listens for one utterance, streaming partial words to the UI.
  Future<String> _listen() async {
    _host.state = _host.state.copyWith(
      status: ConversationStatus.listening,
      clearError: true,
      clearPartial: true,
    );
    final text = await _ref.read(speechServiceProvider).listenOnce(onPartial: _onPartial);
    return text.trim();
  }

  /// After an empty utterance, show a helpful message only if the recognizer
  /// actually failed. Plain silence (nothing said) is not an error and leaves the
  /// state clean.
  void _surfaceListenError() {
    final message = speechErrorMessage(_ref.read(speechServiceProvider).lastError);
    _host.state = _host.state.copyWith(
      status: ConversationStatus.idle,
      error: message,
      clearError: message == null,
    );
  }

  /// Live partial transcript, shown on screen while the learner is speaking.
  void _onPartial(String words) {
    if (_host.state.status == ConversationStatus.listening) {
      _host.state = _host.state.copyWith(partialTranscript: words);
    }
  }
}

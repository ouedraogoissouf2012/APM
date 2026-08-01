import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/network/providers.dart';
import '../../../data/models/turn_correction.dart';
import '../../../data/repositories/conversation_repository.dart';
import 'conversation_host.dart';
import 'conversation_providers.dart';
import 'conversation_state.dart';

/// Consumes the streamed reply for ONE turn and voices it (#121).
///
/// Extracted from ConversationViewModel: it is the piece shared by BOTH input
/// modes (hands-free loop and push-to-talk), so it must not know which one drove
/// it. Instead of the old `_conversing` hack — where push-to-talk flipped the
/// loop's intent flag just to keep the reply flowing — the caller passes an
/// `isLive` predicate. The loop passes its own liveness; push-to-talk passes one
/// that is true for the single response. No shared mutable flag between modes.
class ReplyPlayback {
  ReplyPlayback(this._ref, this._host);

  final Ref _ref;
  final ConversationHost _host;

  ConversationRepository get _repo => _ref.read(conversationRepositoryProvider);

  /// Streams the reply sentence by sentence: each sentence is spoken as soon as
  /// it arrives (so the learner hears the first words while the model is still
  /// writing) and the on-screen reply grows in step. Returns whether the caller
  /// should carry on (still live at the end) or stop (stopped, disposed, error).
  ///
  /// [isLive] is checked after every await so a reply resolving after the caller
  /// was stopped or disposed simply bails without touching state.
  Future<bool> streamReplyAndSpeak(
    int sessionId,
    String heard, {
    required bool Function() isLive,
  }) async {
    final speech = _ref.read(speechServiceProvider);
    final audio = _ref.read(audioPlaybackProvider);
    // Server-side neural voice? Then the reply arrives as audio clips to play;
    // otherwise fall back to the on-device system voice. Defaults to false
    // (on-device) if the backend/config is unreachable.
    final serverTts = await _ref.read(serverTtsProvider.future);
    final buffer = StringBuffer();
    var hasText = false;
    try {
      final events = _repo.streamTurn(sessionId, heard);
      await for (final event in events) {
        if (!isLive()) return false;
        switch (event) {
          case ReplySentence(:final text):
            buffer.write(hasText ? ' $text' : text);
            _setAssistantReply(buffer.toString());
            hasText = true;
            // Only speak on-device when the backend is NOT sending audio.
            if (!serverTts) await speech.speak(text);
          case AudioClip(:final audioB64, :final mime):
            // Real neural voice: play it (awaits until the clip finishes).
            await audio.playClip(audioB64, mime);
          case CorrectionEvent(:final correction):
            // Attach to the learner's turn -> gold chip under their bubble.
            _attachCorrection(correction);
        }
        if (!isLive()) return false;
      }
    } catch (_) {
      if (_host.mounted) {
        _host.state = _host.state.copyWith(
          status: ConversationStatus.idle,
          error: 'Could not get a reply',
        );
      }
      return false;
    }
    return isLive();
  }

  /// Sets (or replaces) the current assistant turn as its text streams in, and
  /// moves to the speaking state. Replaces the last assistant turn in place so
  /// the transcript shows one growing reply, not a sentence per turn.
  void _setAssistantReply(String content) {
    final turns = [..._host.state.turns];
    if (turns.isNotEmpty && turns.last.role == kRoleAssistant) {
      turns[turns.length - 1] = ConversationTurn(kRoleAssistant, content);
    } else {
      turns.add(ConversationTurn(kRoleAssistant, content));
    }
    _host.state = _host.state.copyWith(
      turns: turns,
      status: ConversationStatus.speaking,
    );
  }

  /// Attaches a grammar correction to the learner's most recent user turn, so
  /// the UI renders the gold correction chip under that bubble.
  void _attachCorrection(TurnCorrection correction) {
    final turns = [..._host.state.turns];
    for (var i = turns.length - 1; i >= 0; i--) {
      if (turns[i].role == kRoleUser) {
        turns[i] = turns[i].withCorrection(correction);
        _host.state = _host.state.copyWith(turns: turns);
        return;
      }
    }
  }
}

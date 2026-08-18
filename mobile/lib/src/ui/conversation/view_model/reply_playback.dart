import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/providers.dart';
import '../../../core/observability/ref_report_error.dart';
import '../../../core/offline/connectivity_controller.dart';
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

  // Set by cancel() so streamReplyAndSpeak's loop stops touching state /
  // enqueuing clips even if the caller's own `isLive` predicate does not
  // account for cancellation (push-to-talk's does not: it only checks
  // `_host.mounted`). Without this, cancel() could stop the CURRENT clip yet
  // the still-running stream keeps enqueuing new ones right after — audibly
  // resuming the assistant's voice moments after the learner tapped Stop.
  bool _cancelled = false;

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
    // Server-side neural voice? Then the reply arrives as audio clips to play;
    // otherwise fall back to the on-device system voice. Defaults to false
    // (on-device) if the backend/config is unreachable.
    final serverTts = await _ref.read(conversationServerTtsProvider.future);
    final buffer = StringBuffer();
    var hasText = false;
    // A fresh turn is always live even if a PRIOR turn was cancelled mid-stream.
    _cancelled = false;
    // A per-turn idempotency key (#261): if this turn is retried at the network
    // layer, the server replays the cached reply instead of re-persisting the
    // transcript or re-charging the quota. Unique per attempt — the same pattern
    // the offline queue uses for the non-streaming turn. Declared OUTSIDE the
    // try block (not inlined into streamTurn's call) so a network failure in the
    // catch below can queue the offline replay under this EXACT SAME key (#313)
    // instead of a fresh one — a try-scoped local would not be visible there.
    final idempotencyKey =
        '$sessionId-${DateTime.now().microsecondsSinceEpoch}';
    try {
      final events = _repo.streamTurn(
        sessionId,
        heard,
        idempotencyKey: idempotencyKey,
      );
      await for (final event in events) {
        if (!isLive() || _cancelled) return false;
        switch (event) {
          case ReplySentence(:final text):
            buffer.write(hasText ? ' $text' : text);
            _setAssistantReply(buffer.toString());
            hasText = true;
            // Only speak on-device when the backend is NOT sending audio.
            if (!serverTts) await speech.speak(text);
          case AudioClip(:final audioB64, :final mime):
            // Real neural voice: QUEUE the clip and keep reading the stream. We
            // must NOT await playback here — a per-sentence clip that plays for a
            // few seconds would otherwise freeze the text stream (and a stuck clip
            // would hang the whole turn). The queue plays clips in order, in the
            // background, while the next sentences keep streaming in.
            _enqueueClip(audioB64, mime);
          case CorrectionEvent(:final correction):
            // Attach to the learner's turn -> gold chip under their bubble.
            _attachCorrection(correction);
        }
        if (!isLive() || _cancelled) return false;
      }
    } catch (e, s) {
      // On a NETWORK failure, don't lose the turn: queue it for replay on
      // reconnect (#127) and tell the learner it will be sent later. A
      // non-network failure keeps the previous generic error.
      final offline =
          e is ApiException && (e.statusCode == 0 || e.code == 'network');
      if (offline) {
        await _ref
            .read(connectivityControllerProvider.notifier)
            .recordFailedTurn(sessionId, heard, idempotencyKey: idempotencyKey);
      } else {
        // #403: a network failure is expected (queued above) and stays quiet;
        // anything else here (a backend 5xx, a malformed stream event) is a
        // silent failure of the app's central flow unless reported.
        _ref.reportError(e, s, context: 'ReplyPlayback.stream');
      }
      if (_host.mounted) {
        _host.state = _host.state.copyWith(
          status: ConversationStatus.idle,
          error: offline
              ? 'Hors ligne — ta phrase sera envoyée à la reconnexion'
              : 'Could not get a reply',
        );
      }
      return false;
    }
    final live = isLive();
    if (live) {
      // #404 (best-effort, defense-in-depth alongside the connectivity_plus
      // listener in connectivity_controller.dart): a successful turn is a
      // stronger signal of ACTUAL reachability than the OS-level connectivity
      // event, which can fire before the network is genuinely usable (e.g. a
      // captive portal). Only bothers when there is something to reconcile.
      final connectivity = _ref.read(connectivityControllerProvider);
      if (connectivity.hasPending || !connectivity.online) {
        unawaited(
          _ref.read(connectivityControllerProvider.notifier).syncPending(),
        );
      }
    }
    return live;
  }

  // Sequential background player for the neural audio clips. Clips are enqueued
  // as they arrive and played one after another (await between them) OFF the
  // stream-reading path, so playback never blocks the text.
  final List<(String, String)> _clipQueue = [];
  Future<void>? _playbackTask;

  void _enqueueClip(String audioB64, String mime) {
    _clipQueue.add((audioB64, mime));
    _playbackTask ??= _drainClips();
  }

  Future<void> _drainClips() async {
    final audio = _ref.read(audioPlaybackProvider);
    try {
      while (_clipQueue.isNotEmpty) {
        final (b64, mime) = _clipQueue.removeAt(0);
        try {
          await audio.playClip(b64, mime);
        } catch (_) {
          // A failed clip must not stop the queue or the conversation.
        }
      }
    } finally {
      _playbackTask = null;
    }
  }

  /// Awaits any in-flight background playback. Used by the loop before it opens
  /// the mic again (so the recognizer never captures the assistant's own neural
  /// voice) and by tests that need the audio finished.
  Future<void> awaitPlayback() async {
    while (_playbackTask != null) {
      await _playbackTask;
    }
  }

  /// Stops and discards any queued or in-flight reply audio — called when the
  /// learner stops or ends the conversation, so the neural voice does not keep
  /// talking after the session is over. Also stops streamReplyAndSpeak's loop
  /// from enqueuing anything more for the turn it may still be mid-stream on
  /// (see `_cancelled`), independent of whatever the caller's `isLive` does.
  Future<void> cancel() async {
    _cancelled = true;
    _clipQueue.clear();
    await _ref.read(audioPlaybackProvider).stop();
    // #314: stop() now unblocks an in-flight play() promptly, but don't wait on
    // _drainClips's own cleanup to notice — clear the flag immediately so a
    // caller that checks/awaits playback right after cancel() (e.g. the loop
    // re-opening the mic) sees "nothing playing" without a stray delay.
    _playbackTask = null;
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

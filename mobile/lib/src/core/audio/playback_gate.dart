import 'dart:async';

/// Bridges a player's "stop" action to an in-flight "wait until playback ends"
/// future, so `stop()` can unblock a caller immediately instead of only via a
/// timeout fallback (#314). Shared by the native (audioplayers) and web
/// (HTMLAudioElement) players: audioplayers' `stop()` fires no completion
/// event, and pausing an `HTMLAudioElement` fires neither 'ended' nor 'error'
/// — without this, a cancelled clip only unblocks after a fixed timeout.
class PlaybackGate {
  Completer<void>? _completer;

  /// Starts a new wait window and returns its completer. The caller awaits
  /// `completer.future` (bounded by its own timeout) and completes it either
  /// on the player's natural end/error event, or via [complete] from [stop].
  Completer<void> start() {
    final completer = Completer<void>();
    _completer = completer;
    return completer;
  }

  /// Completes the CURRENT wait window, if any and not already done. Safe to
  /// call with no window open (e.g. `stop()` before any `play()`).
  void complete() {
    final completer = _completer;
    if (completer != null && !completer.isCompleted) completer.complete();
  }

  /// Clears the wait window, but only if [completer] is still the current one
  /// — a newer [start] may have already replaced it while this one's caller
  /// was unwinding, and clearing then would drop the newer window's owner.
  void clear(Completer<void> completer) {
    if (identical(_completer, completer)) _completer = null;
  }
}

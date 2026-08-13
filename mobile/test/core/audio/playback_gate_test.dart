import 'dart:async';

import 'package:apm/src/core/audio/playback_gate.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('complete() unblocks an in-flight start() immediately (#314)', () async {
    // The core mechanism the fix relies on: native_player.dart/web_player.dart's
    // stop() fires no natural completion event, so it must complete() the gate
    // itself instead of leaving the waiter to a fallback timeout.
    final gate = PlaybackGate();
    final completer = gate.start();
    var resolved = false;
    unawaited(completer.future.then((_) => resolved = true));

    expect(resolved, isFalse);
    gate.complete();
    await Future<void>.delayed(Duration.zero); // let the completion propagate
    expect(resolved, isTrue);
  });

  test('complete() with no start() is a safe no-op', () {
    final gate = PlaybackGate();
    expect(gate.complete, returnsNormally);
  });

  test('complete() is idempotent — a second call never throws '
      '"Future already completed"', () async {
    final gate = PlaybackGate();
    final completer = gate.start();
    gate.complete();
    expect(gate.complete, returnsNormally);
    await completer.future; // still resolves exactly once
  });

  test('clear() only clears the CURRENT window, never a newer one that '
      'already replaced it', () {
    // Guards the race where an old play()'s cleanup runs AFTER a fresh
    // play() has already started a new window.
    final gate = PlaybackGate();
    final first = gate.start();
    final second = gate.start(); // a newer play() started first

    gate.clear(first); // the first window's own (late) cleanup

    gate.complete();
    expect(second.isCompleted, isTrue);
  });

  test('the natural-completion path (an "ended"/onPlayerComplete-style '
      'event) still completes the gate the same way stop() does', () async {
    final gate = PlaybackGate();
    final completer = gate.start();

    gate.complete(); // stands in for either the event handler or stop()

    expect(completer.isCompleted, isTrue);
  });
}

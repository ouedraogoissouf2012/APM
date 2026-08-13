import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';

/// Debounces repeated pushes to the SAME [location] within [cooldown] (#331):
/// unlike `context.go` (idempotent — replaces the current route), `context.push`
/// STACKS. A double-tap on a nav card/button before the first push has navigated
/// away pushes the destination twice — two back-presses to leave, its data
/// provider fetched twice.
///
/// Keyed by the destination location, not a blanket "any push, anywhere" cooldown:
/// two DIFFERENT, deliberate navigations moments apart (e.g. tapping "Réviser"
/// then, after coming back, "Prononcer") must never be debounced against each
/// other — only a repeat of the SAME destination, which is what an accidental
/// double-tap actually produces.
class DebouncedPushGuard {
  DebouncedPushGuard({
    this.cooldown = const Duration(milliseconds: 600),
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  final Duration cooldown;
  final DateTime Function() _clock;

  String? _lastLocation;
  DateTime? _lastPushAt;

  /// True if [location] may be pushed now — and records that it was, so an
  /// immediate repeat is blocked until [cooldown] elapses.
  bool shouldPush(String location) {
    final now = _clock();
    final last = _lastPushAt;
    if (last != null) {
      final elapsed = now.difference(last);
      // A backward clock jump (NTP correction, manual date change — rare but
      // real on a phone) makes `elapsed` negative, which is always < cooldown;
      // without excluding it explicitly, that single event would wrongly look
      // like "still within the cooldown" and silently block this location
      // until real time naturally caught back up to the stale mark. Treat any
      // non-forward elapsed time as "cooldown already over" — the safe
      // default never permanently blocks a route.
      if (_lastLocation == location && !elapsed.isNegative && elapsed < cooldown) {
        return false;
      }
    }
    _lastLocation = location;
    _lastPushAt = now;
    return true;
  }
}

DebouncedPushGuard _sharedGuard = DebouncedPushGuard();

/// Replaces the shared guard (a fresh one by default). Tests MUST call this in
/// `setUp()` before exercising [DebouncedNavigation.debouncedPush]: the guard is
/// a single instance shared by the whole app (so a double-tap is caught
/// regardless of which widget rebuilds between the two taps), which means its
/// state otherwise leaks across test cases — two unrelated tests pushing the
/// same route within the real wall-clock cooldown would spuriously debounce
/// the second one.
@visibleForTesting
void debugResetDebouncedPushGuard([DebouncedPushGuard? guard]) {
  _sharedGuard = guard ?? DebouncedPushGuard();
}

extension DebouncedNavigation on BuildContext {
  /// Like `context.push(location)`, but ignores the call if the SAME
  /// [location] was already pushed within the last [DebouncedPushGuard.cooldown]
  /// (#331).
  void debouncedPush(String location) {
    if (_sharedGuard.shouldPush(location)) push(location);
  }
}

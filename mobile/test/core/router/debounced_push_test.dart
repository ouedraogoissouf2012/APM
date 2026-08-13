import 'package:apm/src/core/router/debounced_push.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('DebouncedPushGuard (#331)', () {
    test('the first push to a location is always allowed', () {
      final guard = DebouncedPushGuard();
      expect(guard.shouldPush('/echo'), isTrue);
    });

    test('a repeat push to the SAME location within the cooldown is blocked', () {
      var now = DateTime(2026, 1, 1, 12, 0, 0);
      final guard = DebouncedPushGuard(
        cooldown: const Duration(milliseconds: 600),
        clock: () => now,
      );

      expect(guard.shouldPush('/echo'), isTrue);
      now = now.add(const Duration(milliseconds: 100));
      expect(guard.shouldPush('/echo'), isFalse); // the accidental double-tap
    });

    test('a push to the SAME location AFTER the cooldown is allowed again', () {
      var now = DateTime(2026, 1, 1, 12, 0, 0);
      final guard = DebouncedPushGuard(
        cooldown: const Duration(milliseconds: 600),
        clock: () => now,
      );

      expect(guard.shouldPush('/echo'), isTrue);
      now = now.add(const Duration(milliseconds: 601));
      expect(guard.shouldPush('/echo'), isTrue); // a genuine, later navigation
    });

    test('exactly at the cooldown boundary is already allowed (strict "<", '
        'so elapsed == cooldown counts as "elapsed")', () {
      var now = DateTime(2026, 1, 1, 12, 0, 0);
      final guard = DebouncedPushGuard(
        cooldown: const Duration(milliseconds: 600),
        clock: () => now,
      );

      expect(guard.shouldPush('/echo'), isTrue);
      now = now.add(const Duration(milliseconds: 600));
      expect(guard.shouldPush('/echo'), isTrue);
    });

    test('a DIFFERENT location is never blocked by another one\'s cooldown — '
        'two deliberate, distinct navigations must never debounce each other',
        () {
      var now = DateTime(2026, 1, 1, 12, 0, 0);
      final guard = DebouncedPushGuard(
        cooldown: const Duration(milliseconds: 600),
        clock: () => now,
      );

      expect(guard.shouldPush('/review'), isTrue);
      now = now.add(const Duration(milliseconds: 1));
      expect(guard.shouldPush('/echo'), isTrue);
    });

    test('returning to a location already visited (not a rapid repeat) is '
        'allowed once the cooldown has elapsed', () {
      var now = DateTime(2026, 1, 1, 12, 0, 0);
      final guard = DebouncedPushGuard(
        cooldown: const Duration(milliseconds: 600),
        clock: () => now,
      );

      expect(guard.shouldPush('/review'), isTrue);
      now = now.add(const Duration(seconds: 5));
      expect(guard.shouldPush('/echo'), isTrue);
      now = now.add(const Duration(seconds: 5));
      expect(guard.shouldPush('/review'), isTrue); // back to review, long after
    });

    test('a backward clock jump between two genuine navigations does not '
        'permanently block the route — a negative elapsed time is NOT treated '
        'as "still in the cooldown"', () {
      var now = DateTime(2026, 1, 1, 12, 0, 0);
      final guard = DebouncedPushGuard(
        cooldown: const Duration(milliseconds: 600),
        clock: () => now,
      );

      expect(guard.shouldPush('/review'), isTrue);
      // NTP correction / manual date change moves the clock BACKWARD.
      now = now.subtract(const Duration(hours: 1));
      expect(guard.shouldPush('/review'), isTrue); // not wrongly debounced
    });
  });
}

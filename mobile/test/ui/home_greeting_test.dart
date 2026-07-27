import 'package:apm/src/ui/home/widgets/home_greeting.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('displayNameFromEmail', () {
    test('takes the local part and capitalises it', () {
      expect(displayNameFromEmail('seven@apm.dev'), 'Seven');
      expect(displayNameFromEmail('marie.claire@x.fr'), 'Marie.claire');
    });

    test('handles empty / malformed input gracefully', () {
      expect(displayNameFromEmail(''), '');
      expect(displayNameFromEmail('@nodomain'), '');
      expect(displayNameFromEmail(null), '');
    });
  });

  group('greetingForHour', () {
    test('morning, afternoon, evening buckets', () {
      expect(greetingForHour(6), 'Good morning');
      expect(greetingForHour(11), 'Good morning');
      expect(greetingForHour(12), 'Good afternoon');
      expect(greetingForHour(17), 'Good afternoon');
      expect(greetingForHour(18), 'Good evening');
      expect(greetingForHour(23), 'Good evening');
    });

    test('late night counts as evening (wraps below morning)', () {
      expect(greetingForHour(0), 'Good evening');
      expect(greetingForHour(5), 'Good evening');
    });

    test('rejects out-of-range hours defensively', () {
      // Defensive: never throw on a bad clock value.
      expect(() => greetingForHour(-1), returnsNormally);
      expect(() => greetingForHour(24), returnsNormally);
    });
  });
}

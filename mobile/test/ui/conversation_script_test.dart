import 'package:apm/src/data/models/session_modes.dart';
import 'package:apm/src/ui/conversation/view_model/conversation_script.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ConversationScript.openingMessage', () {
    test('scenario mode names the scenario in a readable form', () {
      final msg = ConversationScript.openingMessage(
        mode: kSessionModeScenario,
        scenarioId: 'job_interview',
      );
      expect(msg, contains('job interview'));
      expect(msg, isNot(contains('job_interview')));
    });

    test('free mode returns the generic invitation', () {
      final msg = ConversationScript.openingMessage(
        mode: kSessionModeFree,
        scenarioId: null,
      );
      expect(msg, contains('What would you like to talk about'));
    });

    test('scenario mode without an id falls back to the generic invitation', () {
      final msg = ConversationScript.openingMessage(
        mode: kSessionModeScenario,
        scenarioId: null,
      );
      expect(msg, contains('What would you like to talk about'));
    });

    test('is deterministic (pure, no side effects)', () {
      final a = ConversationScript.openingMessage(
        mode: kSessionModeScenario,
        scenarioId: 'travel',
      );
      final b = ConversationScript.openingMessage(
        mode: kSessionModeScenario,
        scenarioId: 'travel',
      );
      expect(a, b);
    });
  });
}

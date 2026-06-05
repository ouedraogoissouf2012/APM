import 'package:apm/src/ui/scenarios/scenarios.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('kScenarios exposes guided scenarios with unique ids', () {
    expect(kScenarios, isNotEmpty);
    final ids = kScenarios.map((s) => s.id).toSet();
    expect(ids.length, kScenarios.length, reason: 'ids must be unique');
    expect(ids, contains('restaurant'));
    expect(ids, contains('job_interview'));
  });

  test('every scenario has a title and a description', () {
    for (final s in kScenarios) {
      expect(s.title, isNotEmpty);
      expect(s.description, isNotEmpty);
    }
  });
}

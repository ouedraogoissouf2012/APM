import 'package:apm/src/data/models/scenarios.dart';
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

  test('scenarioTitle returns the canonical catalog title', () {
    // The history screen used to re-derive "Job Interview" from the id,
    // diverging from the catalog's "Job interview".
    expect(scenarioTitle('job_interview'), 'Job interview');
    expect(scenarioTitle('restaurant'), 'At a restaurant');
  });

  test('scenarioTitle falls back to a readable form for unknown ids', () {
    expect(scenarioTitle('space_station'), 'Space Station');
  });
}

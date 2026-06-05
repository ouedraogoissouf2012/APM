import 'package:apm/src/ui/scenarios/widgets/scenarios_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows the free option and the guided scenarios', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: ScenariosScreen()));

    expect(find.byKey(const Key('free_conversation')), findsOneWidget);
    expect(find.text('At a restaurant'), findsOneWidget);
    expect(find.byKey(const Key('scenario_job_interview')), findsOneWidget);
  });
}

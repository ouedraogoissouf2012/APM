import 'package:apm/src/data/models/debrief.dart';
import 'package:apm/src/data/repositories/debrief_repository.dart';
import 'package:apm/src/ui/debrief/view_model/debrief_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockDebriefRepository extends Mock implements DebriefRepository {}

void main() {
  test(
    'debriefProvider generates and exposes the debrief for a session',
    () async {
      final repo = _MockDebriefRepository();
      when(() => repo.getOrGenerate(1)).thenAnswer(
        (_) async =>
            const Debrief(cefrEstimate: 'B1', summary: 'good', errors: []),
      );
      final c = ProviderContainer(
        overrides: [debriefRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(c.dispose);

      final debrief = await c.read(debriefProvider(1).future);

      expect(debrief.cefrEstimate, 'B1');
      expect(debrief.summary, 'good');
      verify(() => repo.getOrGenerate(1)).called(1);
    },
  );
}

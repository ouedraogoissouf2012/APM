import 'package:apm/src/data/models/debrief.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Debrief.fromJson parses cefr, summary and errors', () {
    final d = Debrief.fromJson({
      'session_id': 1,
      'cefr_estimate': 'A2',
      'summary': 'Nice work',
      'errors': [
        {
          'original': 'i is',
          'correction': 'I am',
          'rule': 'verb to be',
          'error_type': 'grammar',
        },
      ],
    });

    expect(d.cefrEstimate, 'A2');
    expect(d.summary, 'Nice work');
    expect(d.errors.single.original, 'i is');
    expect(d.errors.single.correction, 'I am');
    expect(d.errors.single.rule, 'verb to be');
    expect(d.errors.single.errorType, 'grammar');
  });

  test('Debrief.fromJson handles empty / missing errors', () {
    final d = Debrief.fromJson({'cefr_estimate': 'B1', 'summary': ''});
    expect(d.errors, isEmpty);
  });

  test('Debrief.fromJson ignores a pronunciation_scores field if a stale '
      'cached response still carries one (#332: the backend never sends it, '
      'and the model no longer parses it — this only guards against a crash '
      'if legacy cached data does)', () {
    final d = Debrief.fromJson({
      'cefr_estimate': 'B1',
      'summary': '',
      'pronunciation_scores': [
        {'word': 'think', 'score': 0.9},
      ],
    });
    expect(d.cefrEstimate, 'B1'); // parses normally, extra key is a no-op
  });
}

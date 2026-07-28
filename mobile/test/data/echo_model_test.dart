import 'package:apm/src/data/models/echo.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ShadowingWord', () {
    test('parses score and confidence', () {
      final w = ShadowingWord.fromJson({
        'target': 'ship',
        'heard': true,
        'score': 0.82,
        'confidence': 0.8,
      });
      expect(w.score, 0.82);
      expect(w.confidence, 0.8);
      expect(w.hasReliableScore, isTrue);
    });

    test('a null score is not reliable', () {
      final w = ShadowingWord.fromJson({'target': 'ship', 'heard': true});
      expect(w.score, isNull);
      expect(w.hasReliableScore, isFalse);
    });

    test('a low-confidence score is not reliable', () {
      final w = ShadowingWord.fromJson({
        'target': 'ship',
        'heard': true,
        'score': 0.9,
        'confidence': 0.3,
      });
      expect(w.hasReliableScore, isFalse);
    });

    test('a score without confidence is treated as reliable', () {
      final w = ShadowingWord.fromJson({'target': 'ship', 'heard': true, 'score': 0.7});
      expect(w.hasReliableScore, isTrue);
    });
  });

  group('AttemptResult', () {
    test('parses words with scores', () {
      final r = AttemptResult.fromJson({
        'transcript': 'the ship',
        'words': [
          {'target': 'the', 'heard': true, 'score': 0.95, 'confidence': 0.8},
          {'target': 'ship', 'heard': false, 'score': 0.0, 'confidence': 0.8},
        ],
        'missed_words': ['ship'],
        'coaching': 'Short i in ship.',
      });
      expect(r.words, hasLength(2));
      expect(r.words[1].score, 0.0);
      expect(r.isPerfect, isFalse);
    });
  });
}

import 'package:apm/src/data/models/debrief.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('fromJson parses word, phoneme, score and confidence', () {
    final s = PronunciationScore.fromJson({
      'word': 'hello',
      'phoneme': 'həˈloʊ',
      'score': 0.82,
      'confidence': 0.9,
    });

    expect(s.word, 'hello');
    expect(s.phoneme, 'həˈloʊ');
    expect(s.score, 0.82);
    expect(s.confidence, 0.9);
    expect(s.hasReliableScore, isTrue);
  });

  test('hasReliableScore is false when the score is missing', () {
    final s = PronunciationScore.fromJson({'word': 'x'});
    expect(s.score, isNull);
    expect(s.hasReliableScore, isFalse);
  });

  test('hasReliableScore is false when confidence is below the threshold', () {
    const s = PronunciationScore(word: 'x', score: 0.9, confidence: 0.3);
    expect(s.hasReliableScore, isFalse);
  });

  test('hasReliableScore is true when confidence is absent but score is present', () {
    const s = PronunciationScore(word: 'x', score: 0.7);
    expect(s.hasReliableScore, isTrue);
  });

  test('Debrief.fromJson parses pronunciation_scores', () {
    final d = Debrief.fromJson({
      'cefr_estimate': 'A2',
      'summary': '',
      'errors': [],
      'pronunciation_scores': [
        {'word': 'hi', 'score': 0.5, 'confidence': 0.8},
      ],
    });
    expect(d.pronunciationScores.single.word, 'hi');
  });

  test('Debrief.fromJson defaults pronunciation_scores to empty', () {
    final d = Debrief.fromJson({'cefr_estimate': 'A2', 'summary': '', 'errors': []});
    expect(d.pronunciationScores, isEmpty);
  });
}

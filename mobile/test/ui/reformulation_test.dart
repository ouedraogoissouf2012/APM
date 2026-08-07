import 'package:apm/src/ui/conversation/reformulation.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('matches when every corrected word is present (order/extra/case tolerant)', () {
    expect(reformulationMatched('I am happy', 'i am happy'), isTrue);
    // STT often adds filler; extra words are tolerated.
    expect(reformulationMatched('I am happy', 'well I am very happy today'), isTrue);
    // Case and punctuation are ignored.
    expect(reformulationMatched('I went to school', 'I Went, to School!'), isTrue);
  });

  test('does not match when a corrected word is missing', () {
    expect(reformulationMatched('I am happy', 'I happy'), isFalse); // "am" dropped
    expect(reformulationMatched('she runs fast', 'she runs'), isFalse); // "fast" dropped
  });

  test('an empty target never matches', () {
    expect(reformulationMatched('', 'anything'), isFalse);
    expect(reformulationMatched('   ', 'anything'), isFalse);
  });
}

import 'package:apm/src/core/speech/speech_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('maps the uk accent preference to British English', () {
    expect(languageTagForAccent('uk'), 'en-GB');
  });

  test('maps us, unknown and absent accents to American English', () {
    expect(languageTagForAccent('us'), 'en-US');
    expect(languageTagForAccent('??'), 'en-US');
    expect(languageTagForAccent(null), 'en-US');
  });
}

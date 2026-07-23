import 'package:apm/src/core/speech/speech_service.dart';
import 'package:apm/src/ui/conversation/view_model/speech_error_message.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('speechErrorMessage — maps recognizer codes to French guidance', () {
    test('no-speech / no-match invites the learner to try again', () {
      for (final code in ['no-speech', 'error_no_match', 'error_speech_timeout']) {
        final msg = speechErrorMessage(code);
        expect(msg, isNotNull, reason: code);
        expect(msg!.toLowerCase(), contains('entendu'), reason: code);
      }
    });

    test('permission denied tells the learner to allow the microphone', () {
      for (final code in ['not-allowed', 'error_permission']) {
        final msg = speechErrorMessage(code);
        expect(msg, isNotNull, reason: code);
        expect(msg!.toLowerCase(), contains('micro'), reason: code);
      }
    });

    test('network failure mentions the connection', () {
      final msg = speechErrorMessage('error_network');
      expect(msg, isNotNull);
      expect(msg!.toLowerCase(), contains('connexion'));
    });

    test('recognizer busy asks the learner to retry in a moment', () {
      final msg = speechErrorMessage(SpeechErrors.recognizerBusy);
      expect(msg, isNotNull);
      expect(msg!.toLowerCase(), contains('instant'));
    });

    test('every message is in French, non-blaming, and non-empty', () {
      const codes = [
        'no-speech',
        'not-allowed',
        'error_network',
        SpeechErrors.recognizerBusy,
        SpeechErrors.startFailed,
        'error_audio',
      ];
      for (final code in codes) {
        final msg = speechErrorMessage(code);
        expect(msg, isNotNull, reason: code);
        expect(msg!.trim(), isNotEmpty, reason: code);
        // Non-blaming: never says the learner is wrong.
        expect(msg.toLowerCase(), isNot(contains('erreur')), reason: code);
      }
    });

    test('null for an unknown or empty code (caller decides the fallback)', () {
      expect(speechErrorMessage('some-unheard-of-code'), isNull);
      expect(speechErrorMessage(''), isNull);
      expect(speechErrorMessage(null), isNull);
    });
  });
}

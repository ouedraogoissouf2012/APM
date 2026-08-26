import '../../../core/speech/speech_service.dart';

/// Shown when STT returns nothing: idle, retap possible, not a silent stop.
const String kHeardNothingMessage = "Je n'ai pas entendu — retape";

/// Turns a recognizer error code into warm, non-blaming French guidance for
/// the learner, or null when the code is unknown/empty (the caller then keeps
/// its own generic fallback). Pure function: one responsibility, fully testable.
///
/// Accepts both the native `speech_to_text` codes (`error_no_match`,
/// `error_permission`, …) and this app's [SpeechErrors] codes.
String? speechErrorMessage(String? code) {
  if (code == null || code.isEmpty) return null;

  return switch (code) {
    'no-speech' ||
    'error_no_match' ||
    'error_speech_timeout' =>
      "Je ne t'ai pas entendu. Parle un peu plus près du micro et réessaie.",
    'not-allowed' ||
    'error_permission' =>
      "Autorise l'accès au micro pour que je puisse t'écouter.",
    'error_network' ||
    'error_network_timeout' =>
      'La reconnaissance a besoin de connexion. Vérifie ta connexion internet.',
    'error_audio' =>
      "Je n'arrive pas à capter le son. Vérifie ton micro et réessaie.",
    SpeechErrors.recognizerBusy =>
      'Un instant, je reprends mon souffle. Touche encore pour parler.',
    SpeechErrors.startFailed =>
      "Le micro n'a pas pu démarrer. Touche encore pour réessayer.",
    _ => null,
  };
}

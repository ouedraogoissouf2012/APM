/// The learner's voice consents (#128). Protective by default: transcription on,
/// everything else off.
class VoiceConsent {
  const VoiceConsent({
    required this.transcription,
    required this.scoring,
    required this.b2bShare,
    required this.modelTraining,
  });

  final bool transcription;
  final bool scoring;
  final bool b2bShare;
  final bool modelTraining;

  factory VoiceConsent.fromJson(Map<String, dynamic> json) => VoiceConsent(
    transcription: json['transcription'] as bool? ?? true,
    scoring: json['scoring'] as bool? ?? false,
    b2bShare: json['b2b_share'] as bool? ?? false,
    modelTraining: json['model_training'] as bool? ?? false,
  );
}

import 'pronunciation_scoring.dart';

/// A single correction in the debrief: the learner's original, the fix, the
/// rule, a fuller explanation, correct examples, and alternative phrasings.
class DebriefError {
  const DebriefError({
    required this.original,
    required this.correction,
    required this.rule,
    required this.errorType,
    this.explanation = '',
    this.examples = const [],
    this.alternatives = const [],
  });

  final String original;
  final String correction;
  final String rule;
  final String errorType;
  final String explanation;
  final List<String> examples;
  final List<String> alternatives;

  /// Whether there is teaching content beyond the one-line before→after.
  bool get hasDetails =>
      explanation.isNotEmpty || examples.isNotEmpty || alternatives.isNotEmpty;

  static List<String> _stringList(dynamic value) =>
      ((value as List?) ?? const []).map((e) => e as String).toList();

  factory DebriefError.fromJson(Map<String, dynamic> json) => DebriefError(
    original: json['original'] as String,
    correction: json['correction'] as String,
    rule: json['rule'] as String,
    errorType: json['error_type'] as String,
    explanation: json['explanation'] as String? ?? '',
    examples: _stringList(json['examples']),
    alternatives: _stringList(json['alternatives']),
  );
}

class PronunciationScore {
  const PronunciationScore({
    required this.word,
    this.score,
    this.phoneme,
    this.confidence,
  });

  final String word;
  final String? phoneme;
  final double? score;
  final double? confidence;

  bool get hasReliableScore =>
      score != null &&
      (confidence == null || confidence! >= kPronunciationReliableConfidence);

  factory PronunciationScore.fromJson(Map<String, dynamic> json) =>
      PronunciationScore(
        word: json['word'] as String,
        phoneme: json['phoneme'] as String?,
        score: (json['score'] as num?)?.toDouble(),
        confidence: (json['confidence'] as num?)?.toDouble(),
      );
}

/// The end-of-session debrief: CEFR estimate, a short summary, and corrections.
class Debrief {
  const Debrief({
    required this.cefrEstimate,
    required this.summary,
    required this.errors,
    this.pronunciationScores = const [],
  });

  final String cefrEstimate;
  final String summary;
  final List<DebriefError> errors;
  final List<PronunciationScore> pronunciationScores;

  factory Debrief.fromJson(Map<String, dynamic> json) => Debrief(
    cefrEstimate: json['cefr_estimate'] as String,
    summary: json['summary'] as String,
    errors: ((json['errors'] as List?) ?? const [])
        .map((e) => DebriefError.fromJson(e as Map<String, dynamic>))
        .toList(),
    pronunciationScores: ((json['pronunciation_scores'] as List?) ?? const [])
        .map((e) => PronunciationScore.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

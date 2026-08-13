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

/// The end-of-session debrief: CEFR estimate, a short summary, and corrections.
class Debrief {
  const Debrief({
    required this.cefrEstimate,
    required this.summary,
    required this.errors,
  });

  final String cefrEstimate;
  final String summary;
  final List<DebriefError> errors;

  factory Debrief.fromJson(Map<String, dynamic> json) => Debrief(
    cefrEstimate: json['cefr_estimate'] as String,
    summary: json['summary'] as String,
    errors: ((json['errors'] as List?) ?? const [])
        .map((e) => DebriefError.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

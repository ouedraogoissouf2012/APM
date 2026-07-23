/// A grammar correction for one learner utterance, shown as a gold chip during
/// the conversation (the mistake, the fix, a short rule, and alternative
/// phrasings — the "grammar options"). Mirrors the backend `correction` SSE event.
class TurnCorrection {
  const TurnCorrection({
    required this.original,
    required this.correction,
    required this.rule,
    this.alternatives = const [],
  });

  final String original;
  final String correction;
  final String rule;
  final List<String> alternatives;

  factory TurnCorrection.fromJson(Map<String, dynamic> json) => TurnCorrection(
    original: json['original'] as String? ?? '',
    correction: json['correction'] as String? ?? '',
    rule: json['rule'] as String? ?? '',
    alternatives: ((json['alternatives'] as List?) ?? const [])
        .map((e) => e as String)
        .toList(),
  );
}

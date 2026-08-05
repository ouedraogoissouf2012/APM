/// Before/after proof of progress for a skill (#126): the factual delta between
/// the learner's first and latest session on it (from the debriefs, not a score).
class Proof {
  const Proof({
    required this.skill,
    required this.baselineSessionId,
    required this.latestSessionId,
    required this.baselineStartedAt,
    required this.latestStartedAt,
    required this.baselineCefr,
    required this.latestCefr,
    required this.resolved,
    required this.newOrWorse,
  });

  final String skill;
  final int baselineSessionId;
  final int latestSessionId;
  final DateTime baselineStartedAt;
  final DateTime latestStartedAt;
  final String baselineCefr;
  final String latestCefr;

  /// Error types the learner made at baseline and no longer makes.
  final List<String> resolved;

  /// Error types that appeared or got worse since baseline (honest regressions).
  final List<String> newOrWorse;

  factory Proof.fromJson(Map<String, dynamic> json) => Proof(
    skill: json['skill'] as String,
    baselineSessionId: json['baseline_session_id'] as int,
    latestSessionId: json['latest_session_id'] as int,
    baselineStartedAt: DateTime.parse(json['baseline_started_at'] as String),
    latestStartedAt: DateTime.parse(json['latest_started_at'] as String),
    baselineCefr: json['baseline_cefr'] as String,
    latestCefr: json['latest_cefr'] as String,
    resolved: ((json['resolved'] as List?) ?? const [])
        .map((e) => e as String)
        .toList(),
    newOrWorse: ((json['new_or_worse'] as List?) ?? const [])
        .map((e) => e as String)
        .toList(),
  );
}

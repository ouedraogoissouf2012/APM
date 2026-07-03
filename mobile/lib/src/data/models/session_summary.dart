class SessionSummary {
  const SessionSummary({
    required this.id,
    required this.mode,
    required this.startedAt,
    required this.scenarioId,
    required this.durationMinutes,
    required this.cefrEstimate,
  });

  final int id;
  final String mode;
  final DateTime startedAt;
  final String? scenarioId;
  final double? durationMinutes;
  final String? cefrEstimate;

  factory SessionSummary.fromJson(Map<String, dynamic> json) => SessionSummary(
    id: json['id'] as int,
    mode: json['mode'] as String,
    startedAt: DateTime.parse(json['started_at'] as String),
    scenarioId: json['scenario_id'] as String?,
    durationMinutes: (json['duration_minutes'] as num?)?.toDouble(),
    cefrEstimate: json['cefr_estimate'] as String?,
  );
}

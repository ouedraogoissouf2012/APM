import 'session_summary.dart';

class ProgressSnapshot {
  const ProgressSnapshot({
    required this.sessions,
    required this.cefrTrend,
    required this.recurringErrors,
  });

  final List<SessionSummary> sessions;
  final List<CefrPoint> cefrTrend;
  final List<RecurringError> recurringErrors;

  bool get isEmpty => sessions.isEmpty;
}

class CefrPoint {
  const CefrPoint({
    required this.sessionId,
    required this.startedAt,
    required this.level,
  });

  final int sessionId;
  final DateTime startedAt;
  final String level;

  factory CefrPoint.fromJson(Map<String, dynamic> json) => CefrPoint(
    sessionId: json['session_id'] as int,
    startedAt: DateTime.parse(json['started_at'] as String),
    level: json['level'] as String,
  );
}

class RecurringError {
  const RecurringError({
    required this.errorType,
    required this.count,
    required this.latestCorrection,
  });

  final String errorType;
  final int count;
  final String latestCorrection;

  factory RecurringError.fromJson(Map<String, dynamic> json) => RecurringError(
    errorType: json['error_type'] as String,
    count: json['count'] as int,
    latestCorrection: (json['latest_correction'] as String?) ?? '',
  );
}

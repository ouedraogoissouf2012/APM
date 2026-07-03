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
}

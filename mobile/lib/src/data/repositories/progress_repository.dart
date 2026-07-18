import '../../core/network/api_exception.dart';
import '../../core/network/authenticated_api_client.dart';
import '../models/debrief.dart';
import '../models/progress_snapshot.dart';
import '../models/session_summary.dart';

class ProgressRepository {
  ProgressRepository(this._api);

  /// How many recent completed sessions we fetch debriefs for (bounds the
  /// number of network calls when computing recurring errors).
  static const int kRecentDebriefsWindow = 5;

  /// How many recurring error types are surfaced to the learner.
  static const int kMaxRecurringErrors = 3;

  final AuthenticatedApiClient _api;

  Future<ProgressSnapshot> load() async {
    final sessions = await _loadSessions();
    final completedSessions = sessions
        .where((session) => session.cefrEstimate != null)
        .take(kRecentDebriefsWindow)
        .toList();
    final debriefs = <Debrief>[];

    for (final session in completedSessions) {
      final debrief = await _loadDebriefIfAvailable(session.id);
      if (debrief != null) debriefs.add(debrief);
    }

    return ProgressSnapshot(
      sessions: sessions,
      cefrTrend: _buildTrend(sessions),
      recurringErrors: _buildRecurringErrors(debriefs),
    );
  }

  Future<List<SessionSummary>> _loadSessions() async {
    final json = await _api.getList('/sessions');
    return json
        .map((item) => SessionSummary.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<Debrief?> _loadDebriefIfAvailable(int sessionId) async {
    try {
      final json = await _api.getJson('/sessions/$sessionId/debrief');
      return Debrief.fromJson(json);
    } on ApiException catch (error) {
      if (error.statusCode == 404) return null;
      rethrow;
    }
  }

  List<CefrPoint> _buildTrend(List<SessionSummary> sessions) {
    final points =
        sessions
            .where((session) => session.cefrEstimate != null)
            .map(
              (session) => CefrPoint(
                sessionId: session.id,
                startedAt: session.startedAt,
                level: session.cefrEstimate!,
              ),
            )
            .toList()
          ..sort((a, b) => a.startedAt.compareTo(b.startedAt));
    return points;
  }

  List<RecurringError> _buildRecurringErrors(List<Debrief> debriefs) {
    final counts = <String, int>{};
    final latestCorrections = <String, String>{};

    for (final debrief in debriefs) {
      for (final error in debrief.errors) {
        final type = error.errorType.trim().isEmpty
            ? 'other'
            : error.errorType.trim();
        counts[type] = (counts[type] ?? 0) + 1;
        latestCorrections[type] = error.correction;
      }
    }

    final recurring =
        counts.entries
            .map(
              (entry) => RecurringError(
                errorType: entry.key,
                count: entry.value,
                latestCorrection: latestCorrections[entry.key] ?? '',
              ),
            )
            .toList()
          ..sort((a, b) {
            final byCount = b.count.compareTo(a.count);
            if (byCount != 0) return byCount;
            return a.errorType.compareTo(b.errorType);
          });

    return recurring.take(kMaxRecurringErrors).toList();
  }
}

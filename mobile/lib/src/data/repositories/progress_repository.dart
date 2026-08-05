import '../../core/network/authenticated_api_client.dart';
import '../models/progress_snapshot.dart';
import '../models/session_summary.dart';

class ProgressRepository {
  ProgressRepository(this._api);

  final AuthenticatedApiClient _api;

  /// Loads the learner's progress in TWO requests (was 1 + N):
  ///   - GET /sessions        → the session history list
  ///   - GET /me/progress     → the CEFR trend + recurring errors, aggregated
  ///                            server-side (no more one-debrief-per-session loop)
  Future<ProgressSnapshot> load() async {
    final sessions = await _loadSessions();
    final progress = await _api.getJson('/me/progress');

    final trend = ((progress['cefr_trend'] as List?) ?? const [])
        .map((e) => CefrPoint.fromJson(e as Map<String, dynamic>))
        .toList();
    final recurring = ((progress['recurring_errors'] as List?) ?? const [])
        .map((e) => RecurringError.fromJson(e as Map<String, dynamic>))
        .toList();

    return ProgressSnapshot(
      sessions: sessions,
      cefrTrend: trend,
      recurringErrors: recurring,
    );
  }

  Future<List<SessionSummary>> _loadSessions() async {
    final json = await _api.getList('/sessions');
    return json
        .map((item) => SessionSummary.fromJson(item as Map<String, dynamic>))
        .toList();
  }
}

import '../../core/network/authenticated_api_client.dart';
import '../models/session_summary.dart';

class SessionHistoryRepository {
  SessionHistoryRepository(this._api);

  final AuthenticatedApiClient _api;

  Future<List<SessionSummary>> listRecent() async {
    final json = await _api.getList('/sessions');
    return json
        .map((item) => SessionSummary.fromJson(item as Map<String, dynamic>))
        .toList();
  }
}

import '../../core/network/authenticated_api_client.dart';
import '../../core/network/api_exception.dart';
import '../models/debrief.dart';

class DebriefRepository {
  DebriefRepository(this._api);

  final AuthenticatedApiClient _api;

  Future<Debrief> get(int sessionId) async {
    final json = await _api.getJson('/sessions/$sessionId/debrief');
    return Debrief.fromJson(json);
  }

  /// Generates (and returns) the debrief for a finished session.
  Future<Debrief> generate(int sessionId) async {
    final json = await _api.postJson('/sessions/$sessionId/debrief');
    return Debrief.fromJson(json);
  }

  Future<Debrief> getOrGenerate(int sessionId) async {
    try {
      return await get(sessionId);
    } on ApiException catch (e) {
      if (e.statusCode != 404) rethrow;
      return generate(sessionId);
    }
  }
}

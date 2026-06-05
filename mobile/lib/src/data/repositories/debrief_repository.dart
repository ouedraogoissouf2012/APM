import '../../core/network/api_client.dart';
import '../../core/storage/token_storage.dart';
import '../models/debrief.dart';

class DebriefRepository {
  DebriefRepository(this._api, this._storage);

  final ApiClient _api;
  final TokenStorage _storage;

  /// Generates (and returns) the debrief for a finished session.
  Future<Debrief> generate(int sessionId) async {
    final json = await _api.postJson(
      '/sessions/$sessionId/debrief',
      bearer: await _storage.readAccessToken(),
    );
    return Debrief.fromJson(json);
  }
}

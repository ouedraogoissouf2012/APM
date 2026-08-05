import '../../core/network/api_exception.dart';
import '../../core/network/authenticated_api_client.dart';
import '../models/proof.dart';

/// Reads the before/after proof for a skill. Returns null when there isn't yet
/// enough history to compare (the backend answers 404).
class ProofRepository {
  ProofRepository(this._api);

  final AuthenticatedApiClient _api;

  Future<Proof?> forSkill(String skill) async {
    try {
      final json = await _api.getJson('/me/proof/$skill');
      return Proof.fromJson(json);
    } on ApiException catch (e) {
      if (e.statusCode == 404) return null; // not enough sessions yet
      rethrow;
    }
  }
}

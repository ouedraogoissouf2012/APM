import '../../core/network/authenticated_api_client.dart';
import '../models/mission.dart';

/// Compiles and fetches missions (the "prep for my real call/interview" flow).
class MissionRepository {
  MissionRepository(this._api);

  final AuthenticatedApiClient _api;

  /// Compiles a real document (offer/CV/pitch/topic/freeform) into a simulation
  /// brief: persona, goal, likely questions.
  Future<Mission> compile({
    required MissionSourceType sourceType,
    required String content,
  }) async {
    final json = await _api.postJson(
      '/missions',
      body: {'source_type': sourceType.wire, 'content': content},
    );
    return Mission.fromJson(json);
  }

  Future<Mission> get(int missionId) async {
    final json = await _api.getJson('/missions/$missionId');
    return Mission.fromJson(json);
  }
}

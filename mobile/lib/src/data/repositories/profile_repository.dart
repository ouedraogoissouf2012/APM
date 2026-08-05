import '../../core/network/authenticated_api_client.dart';
import '../models/profile.dart';

class ProfileRepository {
  ProfileRepository(this._api);

  final AuthenticatedApiClient _api;

  Future<Profile> getProfile() async {
    final json = await _api.getJson('/me/profile');
    return Profile.fromJson(json);
  }

  Future<Profile> updateProfile({
    List<String>? interests,
    String? goal,
    String? correctionIntensity,
    String? accent,
    String? memorySummary,
  }) async {
    // Null fields are omitted (leave unchanged); an explicit "" for
    // memorySummary is sent and clears the memory server-side.
    final json = await _api.putJson(
      '/me/profile',
      body: {
        'interests': ?interests,
        'goal': ?goal,
        'correction_intensity': ?correctionIntensity,
        'accent': ?accent,
        'memory_summary': ?memorySummary,
      },
    );
    return Profile.fromJson(json);
  }
}

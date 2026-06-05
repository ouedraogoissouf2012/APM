import '../../core/network/api_client.dart';
import '../../core/storage/token_storage.dart';
import '../models/profile.dart';

class ProfileRepository {
  ProfileRepository(this._api, this._storage);

  final ApiClient _api;
  final TokenStorage _storage;

  Future<Profile> getProfile() async {
    final json = await _api.getJson('/me/profile', bearer: await _storage.readAccessToken());
    return Profile.fromJson(json);
  }

  Future<Profile> updateProfile({
    List<String>? interests,
    String? goal,
    String? correctionIntensity,
    String? accent,
  }) async {
    final json = await _api.putJson(
      '/me/profile',
      body: {
        'interests': ?interests,
        'goal': ?goal,
        'correction_intensity': ?correctionIntensity,
        'accent': ?accent,
      },
      bearer: await _storage.readAccessToken(),
    );
    return Profile.fromJson(json);
  }
}

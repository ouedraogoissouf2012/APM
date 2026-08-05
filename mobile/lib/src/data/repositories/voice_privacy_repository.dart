import '../../core/network/authenticated_api_client.dart';
import '../models/voice_consent.dart';

/// Reads/updates voice consents and exports/erases voice-derived data (#128).
class VoicePrivacyRepository {
  VoicePrivacyRepository(this._api);

  final AuthenticatedApiClient _api;

  Future<VoiceConsent> getConsent() async {
    final json = await _api.getJson('/me/voice-consent');
    return VoiceConsent.fromJson(json);
  }

  /// Updates a single consent (the backend accepts a partial body).
  Future<VoiceConsent> setConsent(String field, bool value) async {
    final json = await _api.putJson('/me/voice-consent', body: {field: value});
    return VoiceConsent.fromJson(json);
  }

  /// Exports the learner's voice-derived data (utterances + vocabulary).
  Future<Map<String, dynamic>> exportData() =>
      _api.postJson('/me/voice-data/export');

  /// Erases the learner's voice-derived data; returns the deleted counts.
  Future<Map<String, dynamic>> eraseData() async {
    final json = await _api.deleteJson('/me/voice-data');
    return (json['deleted'] as Map<String, dynamic>?) ?? const {};
  }
}

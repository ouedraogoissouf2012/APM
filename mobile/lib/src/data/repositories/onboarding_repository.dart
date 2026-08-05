import '../../core/network/authenticated_api_client.dart';

/// The outcome of an onboarding placement: the starting level the backend
/// estimated, and the interests/goal it saved to the profile.
class PlacementResult {
  const PlacementResult({
    required this.cefrLevel,
    required this.interests,
    required this.goal,
  });

  final String cefrLevel;
  final List<String> interests;
  final String goal;

  factory PlacementResult.fromJson(Map<String, dynamic> json) => PlacementResult(
    cefrLevel: json['cefr_level'] as String,
    interests: ((json['interests'] as List?) ?? const [])
        .map((e) => e as String)
        .toList(),
    goal: (json['goal'] as String?) ?? '',
  );
}

/// Submits the onboarding placement (spoken answers + interests/goal) so the
/// backend estimates a starting CEFR level and pre-fills the profile.
class OnboardingRepository {
  OnboardingRepository(this._api);

  final AuthenticatedApiClient _api;

  Future<PlacementResult> submitPlacement({
    required List<String> answers,
    required List<String> interests,
    required String goal,
  }) async {
    final json = await _api.postJson(
      '/onboarding/placement',
      body: {'answers': answers, 'interests': interests, 'goal': goal},
    );
    return PlacementResult.fromJson(json);
  }
}

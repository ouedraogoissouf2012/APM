import '../../core/network/authenticated_api_client.dart';
import '../models/streak.dart';

/// Reads the learner's streak/weekly-goal and updates the goal.
class StreakRepository {
  StreakRepository(this._api);

  final AuthenticatedApiClient _api;

  Future<Streak> load() async {
    final json = await _api.getJson('/me/streak');
    return Streak.fromJson(json);
  }

  Future<Streak> setWeeklyGoal(int minutes) async {
    final json = await _api.putJson(
      '/me/streak/goal',
      body: {'weekly_goal_minutes': minutes},
    );
    return Streak.fromJson(json);
  }
}

import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/streak_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  late _MockApiClient api;
  late StreakRepository repo;

  setUp(() {
    api = _MockApiClient();
    repo = StreakRepository(api);
  });

  test('load parses the streak snapshot and weekly progress', () async {
    when(() => api.getJson('/me/streak')).thenAnswer(
      (_) async => {
        'current_streak': 5,
        'longest_streak': 9,
        'weekly_goal_minutes': 30,
        'minutes_this_week': 15,
      },
    );

    final streak = await repo.load();
    expect(streak.currentStreak, 5);
    expect(streak.longestStreak, 9);
    expect(streak.weeklyProgress, 0.5); // 15 / 30
  });

  test('weeklyProgress is clamped to 1.0 when the goal is exceeded', () async {
    when(() => api.getJson('/me/streak')).thenAnswer(
      (_) async => {
        'current_streak': 1,
        'longest_streak': 1,
        'weekly_goal_minutes': 30,
        'minutes_this_week': 45,
      },
    );
    final streak = await repo.load();
    expect(streak.weeklyProgress, 1.0);
  });

  test('setWeeklyGoal PUTs the goal and parses the refreshed snapshot', () async {
    Map<String, dynamic>? sentBody;
    when(
      () => api.putJson('/me/streak/goal', body: any(named: 'body')),
    ).thenAnswer((invocation) async {
      sentBody = invocation.namedArguments[#body] as Map<String, dynamic>;
      return {
        'current_streak': 5,
        'longest_streak': 9,
        'weekly_goal_minutes': 60,
        'minutes_this_week': 15,
      };
    });

    final streak = await repo.setWeeklyGoal(60);
    expect(sentBody!['weekly_goal_minutes'], 60);
    expect(streak.weeklyGoalMinutes, 60);
  });
}

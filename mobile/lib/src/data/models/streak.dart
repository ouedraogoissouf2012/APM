/// The learner's habit snapshot: consecutive active days plus this week's
/// practised minutes against their weekly goal.
class Streak {
  const Streak({
    required this.currentStreak,
    required this.longestStreak,
    required this.weeklyGoalMinutes,
    required this.minutesThisWeek,
  });

  final int currentStreak;
  final int longestStreak;
  final int weeklyGoalMinutes;
  final int minutesThisWeek;

  /// 0.0..1.0 progress toward the weekly goal (clamped).
  double get weeklyProgress => weeklyGoalMinutes <= 0
      ? 0
      : (minutesThisWeek / weeklyGoalMinutes).clamp(0.0, 1.0);

  factory Streak.fromJson(Map<String, dynamic> json) => Streak(
    currentStreak: (json['current_streak'] as int?) ?? 0,
    longestStreak: (json['longest_streak'] as int?) ?? 0,
    weeklyGoalMinutes: (json['weekly_goal_minutes'] as int?) ?? 0,
    minutesThisWeek: (json['minutes_this_week'] as int?) ?? 0,
  );
}

class Subscription {
  const Subscription({
    required this.tier,
    required this.isPremium,
    required this.freeDailyMinutes,
    required this.minutesUsedToday,
    this.remainingMinutes,
  });

  final String tier;
  final bool isPremium;
  final int freeDailyMinutes;
  final double minutesUsedToday;
  final double? remainingMinutes;

  bool get quotaWarning =>
      !isPremium &&
      freeDailyMinutes > 0 &&
      minutesUsedToday / freeDailyMinutes >= 0.8;

  factory Subscription.fromJson(Map<String, dynamic> json) => Subscription(
    tier: json['tier'] as String,
    isPremium: json['is_premium'] as bool,
    freeDailyMinutes: json['free_daily_minutes'] as int,
    minutesUsedToday: (json['minutes_used_today'] as num).toDouble(),
    remainingMinutes: (json['remaining_minutes'] as num?)?.toDouble(),
  );
}

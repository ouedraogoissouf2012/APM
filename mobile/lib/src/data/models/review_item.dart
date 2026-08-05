/// One spaced-repetition item: a recurring error type due for review, with the
/// most recent correction seen for it.
class ReviewItem {
  const ReviewItem({
    required this.errorType,
    required this.latestCorrection,
    required this.stage,
    required this.cleanStreak,
    required this.status,
    this.nextReviewAt,
  });

  final String errorType;
  final String latestCorrection;
  final int stage;
  final int cleanStreak;
  final String status; // "due" | "mastered"
  final DateTime? nextReviewAt;

  factory ReviewItem.fromJson(Map<String, dynamic> json) => ReviewItem(
    errorType: json['error_type'] as String,
    latestCorrection: (json['latest_correction'] as String?) ?? '',
    stage: (json['stage'] as int?) ?? 0,
    cleanStreak: (json['clean_streak'] as int?) ?? 0,
    status: (json['status'] as String?) ?? 'due',
    nextReviewAt: json['next_review_at'] == null
        ? null
        : DateTime.parse(json['next_review_at'] as String),
  );
}

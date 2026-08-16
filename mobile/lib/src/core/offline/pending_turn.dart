/// A turn the learner spoke that couldn't be sent yet (offline / network drop),
/// queued locally to replay on reconnect (#127). Carries its own idempotency key
/// so replaying it never duplicates the turn or the quota.
class PendingTurn {
  const PendingTurn({
    required this.sessionId,
    required this.text,
    required this.idempotencyKey,
    this.practicedAt,
  });

  final int sessionId;
  final String text;
  final String idempotencyKey;
  /// When the learner actually spoke (#431). Null on pre-#431 queue rows.
  final DateTime? practicedAt;

  Map<String, dynamic> toJson() => {
    'session_id': sessionId,
    'text': text,
    'idempotency_key': idempotencyKey,
    if (practicedAt != null) 'practiced_at': practicedAt!.toUtc().toIso8601String(),
  };

  factory PendingTurn.fromJson(Map<String, dynamic> json) {
    final raw = json['practiced_at'] as String?;
    return PendingTurn(
      sessionId: json['session_id'] as int,
      text: json['text'] as String,
      idempotencyKey: json['idempotency_key'] as String,
      practicedAt: raw == null ? null : DateTime.tryParse(raw),
    );
  }
}

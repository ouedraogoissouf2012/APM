/// A turn the learner spoke that couldn't be sent yet (offline / network drop),
/// queued locally to replay on reconnect (#127). Carries its own idempotency key
/// so replaying it never duplicates the turn or the quota.
class PendingTurn {
  const PendingTurn({
    required this.sessionId,
    required this.text,
    required this.idempotencyKey,
  });

  final int sessionId;
  final String text;
  final String idempotencyKey;

  Map<String, dynamic> toJson() => {
    'session_id': sessionId,
    'text': text,
    'idempotency_key': idempotencyKey,
  };

  factory PendingTurn.fromJson(Map<String, dynamic> json) => PendingTurn(
    sessionId: json['session_id'] as int,
    text: json['text'] as String,
    idempotencyKey: json['idempotency_key'] as String,
  );
}

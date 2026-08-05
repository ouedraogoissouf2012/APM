/// A vocabulary notebook card: a salient word the learner used, with its
/// phonetic, translation, the learner's own sentence, and a review status.
class VocabularyEntry {
  const VocabularyEntry({
    required this.id,
    required this.word,
    required this.phonetic,
    required this.translation,
    required this.example,
    required this.status,
    this.sessionId,
  });

  final int id;
  final int? sessionId;
  final String word;
  final String phonetic;
  final String translation;
  final String example;
  final String status; // "review" | "known"

  bool get isKnown => status == 'known';

  factory VocabularyEntry.fromJson(Map<String, dynamic> json) => VocabularyEntry(
    id: json['id'] as int,
    sessionId: json['session_id'] as int?,
    word: json['word'] as String,
    phonetic: (json['phonetic'] as String?) ?? '',
    translation: (json['translation'] as String?) ?? '',
    example: (json['example'] as String?) ?? '',
    status: (json['status'] as String?) ?? 'review',
  );

  VocabularyEntry copyWith({String? status}) => VocabularyEntry(
    id: id,
    sessionId: sessionId,
    word: word,
    phonetic: phonetic,
    translation: translation,
    example: example,
    status: status ?? this.status,
  );
}

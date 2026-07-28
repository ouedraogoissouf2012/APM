/// A phrase to shadow (read aloud), plus what it trains and one tip. Mirrors the
/// backend `POST /shadowing/phrase` response.
class ShadowingPhrase {
  const ShadowingPhrase({required this.text, this.focus = 'general', this.tip = ''});

  final String text;
  final String focus;
  final String tip;

  factory ShadowingPhrase.fromJson(Map<String, dynamic> json) => ShadowingPhrase(
    text: json['text'] as String? ?? '',
    focus: json['focus'] as String? ?? 'general',
    tip: json['tip'] as String? ?? '',
  );
}

/// One target word: whether the recognizer heard it, and how clearly.
/// [score] (0..1, null = unknown) is the pronunciation-clarity score;
/// [confidence] (0..1, null = treat as reliable) is how much to trust it.
class ShadowingWord {
  const ShadowingWord({
    required this.target,
    required this.heard,
    this.score,
    this.confidence,
  });

  final String target;
  final bool heard;
  final double? score;
  final double? confidence;

  /// Whether the score is trustworthy enough to color the word (mirrors the
  /// debrief's PronunciationScore.hasReliableScore rule).
  bool get hasReliableScore =>
      score != null && (confidence == null || confidence! >= 0.5);

  factory ShadowingWord.fromJson(Map<String, dynamic> json) => ShadowingWord(
    target: json['target'] as String? ?? '',
    heard: json['heard'] as bool? ?? false,
    score: (json['score'] as num?)?.toDouble(),
    confidence: (json['confidence'] as num?)?.toDouble(),
  );
}

/// The outcome of one spoken attempt. Mirrors `POST /shadowing/attempt`.
class AttemptResult {
  const AttemptResult({
    required this.transcript,
    this.words = const [],
    this.missedWords = const [],
    this.coaching = '',
  });

  final String transcript;
  final List<ShadowingWord> words;
  final List<String> missedWords;
  final String coaching;

  bool get isPerfect => missedWords.isEmpty;

  factory AttemptResult.fromJson(Map<String, dynamic> json) => AttemptResult(
    transcript: json['transcript'] as String? ?? '',
    words: ((json['words'] as List?) ?? const [])
        .map((e) => ShadowingWord.fromJson(e as Map<String, dynamic>))
        .toList(),
    missedWords: ((json['missed_words'] as List?) ?? const [])
        .map((e) => e as String)
        .toList(),
    coaching: json['coaching'] as String? ?? '',
  );
}

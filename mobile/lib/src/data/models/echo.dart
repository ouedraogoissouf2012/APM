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

/// One target word and whether the recognizer heard it.
class ShadowingWord {
  const ShadowingWord({required this.target, required this.heard});

  final String target;
  final bool heard;

  factory ShadowingWord.fromJson(Map<String, dynamic> json) => ShadowingWord(
    target: json['target'] as String? ?? '',
    heard: json['heard'] as bool? ?? false,
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

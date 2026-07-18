/// Pedagogical scoring thresholds for pronunciation feedback — the single
/// source for the score barème, shared by the model (`hasReliableScore`) and
/// the pronunciation map UI.
library;

/// A word/phoneme at or above this score is considered mastered ("strong").
const double kPronunciationStrongThreshold = 0.8;

/// Between this and the strong threshold: worth reviewing ("review");
/// below: "needs practice".
const double kPronunciationReviewThreshold = 0.6;

/// Minimum recognizer confidence for a score to be shown at all — an honest
/// display: below this we say "not enough data" instead of guessing.
const double kPronunciationReliableConfidence = 0.5;

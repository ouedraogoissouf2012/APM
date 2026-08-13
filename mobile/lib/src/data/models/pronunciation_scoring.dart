/// Pedagogical scoring thresholds for pronunciation feedback — the single
/// source for the score barème. Currently used by the echo/shadowing
/// feature (`EchoPhonemeScore.isStrong`/`needsPractice`, echo.dart). The
/// debrief's own pronunciation display (`Debrief.pronunciationScores`,
/// `PronunciationMap`) was removed (#332): the backend never emits
/// `pronunciation_scores` in `DebriefOut`, so that UI was permanently dead —
/// tracked to return once the pronunciation service is wired for debriefs too
/// (#4 Azure). [kPronunciationReliableConfidence] is unused meanwhile, kept
/// for that reconnection rather than deleted.
library;

/// A word/phoneme at or above this score is considered mastered ("strong").
const double kPronunciationStrongThreshold = 0.8;

/// Between this and the strong threshold: worth reviewing ("review");
/// below: "needs practice".
const double kPronunciationReviewThreshold = 0.6;

/// Minimum recognizer confidence for a score to be shown at all — an honest
/// display: below this we say "not enough data" instead of guessing.
const double kPronunciationReliableConfidence = 0.5;

/// Pure matching for the reformulation step (#200): did the learner re-say the
/// CORRECTED sentence? Kept free of I/O and widgets so the (forgiving) rule is
/// unit-testable.
///
/// STT drops/adds small words and never matches punctuation, so an exact string
/// compare is too strict. The honest rule: every content word of the target must
/// be present in what was heard (order-independent, extra words tolerated).
bool reformulationMatched(String target, String heard) {
  final targetWords = _words(target);
  if (targetWords.isEmpty) return false;
  final heardWords = _words(heard).toSet();
  return targetWords.every(heardWords.contains);
}

List<String> _words(String s) => s
    .toLowerCase()
    .replaceAll(RegExp(r'[^a-z0-9\s]'), ' ')
    .split(RegExp(r'\s+'))
    .where((w) => w.isNotEmpty)
    .toList();

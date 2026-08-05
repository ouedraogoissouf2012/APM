/// Human-readable French labels for the backend's canonical error types
/// (`error_taxonomy.py`). Falls back to a de-underscored title for any unknown
/// type so a new backend category never shows up as a raw slug.
String errorTypeLabel(String errorType) {
  const labels = <String, String>{
    'grammar': 'Grammaire',
    'verb_tense': 'Temps du verbe',
    'verb_form': 'Forme du verbe',
    'subject_verb_agreement': 'Accord sujet-verbe',
    'word_order': 'Ordre des mots',
    'article': 'Articles',
    'preposition': 'Prépositions',
    'pronoun': 'Pronoms',
    'plural': 'Pluriels',
    'spelling': 'Orthographe',
    'punctuation': 'Ponctuation',
    'capitalization': 'Majuscules',
    'vocabulary': 'Vocabulaire',
    'word_choice': 'Choix des mots',
    'fluency': 'Aisance',
    'other': 'Divers',
  };
  final known = labels[errorType];
  if (known != null) return known;
  if (errorType.isEmpty) return 'Divers';
  // Unknown type: "some_new_type" -> "Some new type".
  final spaced = errorType.replaceAll('_', ' ');
  return spaced[0].toUpperCase() + spaced.substring(1);
}

/// The source material a mission is compiled from. Mirrors the backend's
/// SourceType literal (offer|cv|pitch|topic|freeform).
enum MissionSourceType {
  offer,
  cv,
  pitch,
  topic,
  freeform;

  /// The wire value the backend expects.
  String get wire => name;

  /// A short French label for the picker.
  String get label => switch (this) {
    MissionSourceType.offer => 'Offre d’emploi',
    MissionSourceType.cv => 'CV',
    MissionSourceType.pitch => 'Pitch',
    MissionSourceType.topic => 'Sujet / soutenance',
    MissionSourceType.freeform => 'Décrire la situation',
  };
}

/// A compiled simulation: who the learner will talk to, the goal, and the
/// questions likely to come up. The backend keeps the system prompt private.
class Mission {
  const Mission({
    required this.id,
    required this.sourceType,
    required this.persona,
    required this.goal,
    required this.likelyQuestions,
  });

  final int id;
  final String sourceType;
  final String persona;
  final String goal;
  final List<String> likelyQuestions;

  factory Mission.fromJson(Map<String, dynamic> json) => Mission(
    id: json['id'] as int,
    sourceType: json['source_type'] as String,
    persona: json['persona'] as String,
    goal: json['goal'] as String,
    likelyQuestions: ((json['likely_questions'] as List?) ?? const [])
        .map((e) => e as String)
        .toList(),
  );
}

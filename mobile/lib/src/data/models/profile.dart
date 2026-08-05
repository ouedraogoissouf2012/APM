/// The learner profile (interests, goal, correction style, accent) plus the
/// memory the assistant keeps about the learner across sessions.
class Profile {
  const Profile({
    required this.interests,
    required this.goal,
    required this.correctionIntensity,
    required this.accent,
    this.memorySummary = '',
  });

  final List<String> interests;
  final String? goal;
  final String correctionIntensity; // "gentle" | ...
  final String accent; // "us" | "uk"

  /// What the assistant remembers about the learner (written by the debrief
  /// after each session). Empty when nothing has been learned yet.
  final String memorySummary;

  factory Profile.fromJson(Map<String, dynamic> json) => Profile(
    interests: ((json['interests'] as List?) ?? const [])
        .map((e) => e as String)
        .toList(),
    goal: json['goal'] as String?,
    correctionIntensity: json['correction_intensity'] as String,
    accent: json['accent'] as String,
    memorySummary: (json['memory_summary'] as String?) ?? '',
  );
}

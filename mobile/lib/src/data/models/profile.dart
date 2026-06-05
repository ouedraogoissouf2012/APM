/// The learner profile (interests, goal, correction style, accent).
class Profile {
  const Profile({
    required this.interests,
    required this.goal,
    required this.correctionIntensity,
    required this.accent,
  });

  final List<String> interests;
  final String? goal;
  final String correctionIntensity; // "gentle" | ...
  final String accent; // "us" | "uk"

  factory Profile.fromJson(Map<String, dynamic> json) => Profile(
        interests: ((json['interests'] as List?) ?? const []).map((e) => e as String).toList(),
        goal: json['goal'] as String?,
        correctionIntensity: json['correction_intensity'] as String,
        accent: json['accent'] as String,
      );
}

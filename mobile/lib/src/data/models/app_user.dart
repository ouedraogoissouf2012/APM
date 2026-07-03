/// Immutable user model. Hand-written (no codegen) to keep the dependency
/// footprint minimal and the build simple to maintain.
class AppUser {
  const AppUser({
    required this.id,
    required this.email,
    required this.nativeLanguage,
    required this.cefrLevel,
    required this.tier,
  });

  final int id;
  final String email;
  final String nativeLanguage;
  final String cefrLevel;
  final String tier;

  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
    id: json['id'] as int,
    email: json['email'] as String,
    nativeLanguage: json['native_language'] as String,
    cefrLevel: json['cefr_level'] as String,
    tier: json['tier'] as String,
  );

  @override
  bool operator ==(Object other) =>
      other is AppUser &&
      other.id == id &&
      other.email == email &&
      other.nativeLanguage == nativeLanguage &&
      other.cefrLevel == cefrLevel &&
      other.tier == tier;

  @override
  int get hashCode => Object.hash(id, email, nativeLanguage, cefrLevel, tier);
}

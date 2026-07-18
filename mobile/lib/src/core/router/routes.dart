import '../../data/models/session_modes.dart';

/// Route paths — single source shared by the router and every screen, so a
/// renamed route cannot silently diverge across files.
abstract final class Routes {
  static const onboarding = '/onboarding';
  static const login = '/login';
  static const register = '/register';
  static const home = '/home';
  static const history = '/history';
  static const conversation = '/conversation';
  static const profile = '/profile';
  static const scenarios = '/scenarios';

  /// Galerie du design system — enregistrée uniquement en debug.
  static const devGallery = '/dev/gallery';

  /// Pattern registered in the router; use [debrief] to build a concrete path.
  static const debriefPattern = '/debrief/:sessionId';

  static String debrief(int sessionId) => '/debrief/$sessionId';

  static String conversationWith({required String mode, String? scenarioId}) =>
      scenarioId == null
      ? '$conversation?mode=$mode'
      : '$conversation?mode=$mode&scenario=$scenarioId';

  static String get conversationFree => conversationWith(mode: kSessionModeFree);
}

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../ui/auth/view_model/auth_view_model.dart';
import '../../ui/auth/widgets/login_screen.dart';
import '../../ui/auth/widgets/register_screen.dart';
import '../../ui/conversation/widgets/conversation_screen.dart';
import '../../ui/debrief/widgets/debrief_screen.dart';
import '../../ui/echo/widgets/echo_screen.dart';
import '../../ui/history/widgets/session_history_screen.dart';
import '../../ui/minimal_pairs/widgets/minimal_pairs_screen.dart';
import '../../ui/home/widgets/home_screen.dart';
import '../../ui/onboarding/widgets/onboarding_screen.dart';
import '../../ui/onboarding/widgets/placement_screen.dart';
import '../../ui/profile/widgets/memory_screen.dart';
import '../../ui/profile/widgets/profile_screen.dart';
import '../../ui/scenarios/widgets/scenarios_screen.dart';
import '../../dev/gallery_page.dart';
import 'routes.dart';

/// The app router. Built once; a [ValueNotifier] tied to the auth state drives
/// go_router's redirect re-evaluation on login/logout (no codegen).
final appRouterProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier<int>(0);
  ref.listen(authViewModelProvider, (_, _) => refresh.value++);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: Routes.onboarding,
    refreshListenable: refresh,
    redirect: (context, state) {
      final auth = ref.read(authViewModelProvider);
      if (auth.isLoading) return null;
      final signedIn = auth.value != null;
      final atPublicEntry =
          state.matchedLocation == Routes.onboarding ||
          state.matchedLocation == Routes.login ||
          state.matchedLocation == Routes.register;
      // La galerie du design system est hors parcours auth (debug only).
      if (kDebugMode && state.matchedLocation == Routes.devGallery) return null;
      if (!signedIn && !atPublicEntry) return Routes.onboarding;
      if (signedIn && atPublicEntry) {
        // A just-registered learner goes through the spoken placement first
        // (skippable); a returning learner from login/onboarding goes home.
        return state.matchedLocation == Routes.register
            ? Routes.placement
            : Routes.home;
      }
      return null;
    },
    routes: [
      GoRoute(
        path: Routes.onboarding,
        builder: (_, _) => const OnboardingScreen(),
      ),
      GoRoute(path: Routes.login, builder: (_, _) => const LoginScreen()),
      GoRoute(path: Routes.register, builder: (_, _) => const RegisterScreen()),
      GoRoute(path: Routes.home, builder: (_, _) => const HomeScreen()),
      GoRoute(
        path: Routes.placement,
        builder: (_, _) => const PlacementScreen(),
      ),
      GoRoute(
        path: Routes.history,
        builder: (_, _) => const SessionHistoryScreen(),
      ),
      GoRoute(
        path: Routes.conversation,
        builder: (_, _) => const ConversationScreen(),
      ),
      GoRoute(
        path: Routes.debriefPattern,
        builder: (_, state) => DebriefScreen(
          sessionId: int.parse(state.pathParameters['sessionId']!),
        ),
      ),
      GoRoute(path: Routes.profile, builder: (_, _) => const ProfileScreen()),
      GoRoute(path: Routes.memory, builder: (_, _) => const MemoryScreen()),
      GoRoute(
        path: Routes.scenarios,
        builder: (_, _) => const ScenariosScreen(),
      ),
      GoRoute(path: Routes.echo, builder: (_, _) => const EchoScreen()),
      GoRoute(
        path: Routes.minimalPairs,
        builder: (_, _) => const MinimalPairsScreen(),
      ),
      if (kDebugMode)
        GoRoute(
          path: Routes.devGallery,
          builder: (_, _) => const GalleryPage(),
        ),
    ],
  );
});

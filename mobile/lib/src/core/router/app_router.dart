import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../ui/auth/view_model/auth_view_model.dart';
import '../../ui/auth/widgets/login_screen.dart';
import '../../ui/auth/widgets/register_screen.dart';
import '../../ui/conversation/widgets/conversation_screen.dart';
import '../../ui/debrief/widgets/debrief_screen.dart';
import '../../ui/history/widgets/session_history_screen.dart';
import '../../ui/home/widgets/home_screen.dart';
import '../../ui/profile/widgets/profile_screen.dart';
import '../../ui/scenarios/widgets/scenarios_screen.dart';

/// The app router. Built once; a [ValueNotifier] tied to the auth state drives
/// go_router's redirect re-evaluation on login/logout (no codegen).
final appRouterProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier<int>(0);
  ref.listen(authViewModelProvider, (_, _) => refresh.value++);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: '/login',
    refreshListenable: refresh,
    redirect: (context, state) {
      final auth = ref.read(authViewModelProvider);
      if (auth.isLoading) return null;
      final signedIn = auth.value != null;
      final atAuth =
          state.matchedLocation == '/login' ||
          state.matchedLocation == '/register';
      if (!signedIn && !atAuth) return '/login';
      if (signedIn && atAuth) return '/home';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(path: '/register', builder: (_, _) => const RegisterScreen()),
      GoRoute(path: '/home', builder: (_, _) => const HomeScreen()),
      GoRoute(
        path: '/history',
        builder: (_, _) => const SessionHistoryScreen(),
      ),
      GoRoute(
        path: '/conversation',
        builder: (_, _) => const ConversationScreen(),
      ),
      GoRoute(
        path: '/debrief/:sessionId',
        builder: (_, state) => DebriefScreen(
          sessionId: int.parse(state.pathParameters['sessionId']!),
        ),
      ),
      GoRoute(path: '/profile', builder: (_, _) => const ProfileScreen()),
      GoRoute(path: '/scenarios', builder: (_, _) => const ScenariosScreen()),
    ],
  );
});

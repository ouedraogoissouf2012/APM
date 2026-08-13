import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// `Override` (used to type userScopedProviders/UserSessionScope.overrides,
// #373) is deliberately kept out of the main flutter_riverpod barrel and
// only re-exported here.
import 'package:flutter_riverpod/misc.dart';

import 'src/core/observability/crash_reporter.dart';
import 'src/core/observability/providers.dart';
import 'src/core/router/app_router.dart';
import 'src/core/theme/app_theme.dart';
import 'src/ui/auth/view_model/auth_view_model.dart';
import 'src/ui/debrief/view_model/debrief_view_model.dart';
import 'src/ui/history/view_model/progress_view_model.dart';
import 'src/ui/home/view_model/streak_view_model.dart';
import 'src/ui/missions/view_model/mission_view_model.dart';
import 'src/ui/privacy/view_model/voice_privacy_view_model.dart';
import 'src/ui/profile/view_model/profile_view_model.dart';
import 'src/ui/proof/view_model/proof_view_model.dart';
import 'src/ui/review/view_model/review_view_model.dart';
import 'src/ui/vocabulary/view_model/vocabulary_view_model.dart';

void main() {
  // Crash-reporting (#236): capture errors that would otherwise vanish
  // without a trace. Three layers, per Flutter's own guidance — each catches
  // errors the others can't: FlutterError.onError for framework/widget build
  // errors, PlatformDispatcher.instance.onError for async errors surfacing to
  // the root zone, and runZonedGuarded's handler as the outermost catch-all
  // for anything that escapes both (e.g. inside main() itself, before the
  // widget tree exists). One reporter instance for all three AND the
  // Riverpod-visible provider, so a breadcrumb left by a view-model and a
  // later crash share one trail.
  final crashReporter = LoggingCrashReporter();
  FlutterError.onError = (details) {
    crashReporter.captureError(
      details.exception,
      details.stack ?? StackTrace.empty,
      context: 'FlutterError',
    );
    FlutterError.presentError(details);
  };
  runZonedGuarded(
    () {
      WidgetsFlutterBinding.ensureInitialized();
      _registerFontLicenses();
      PlatformDispatcher.instance.onError = (error, stack) {
        crashReporter.captureError(error, stack, context: 'PlatformDispatcher');
        return true;
      };
      runApp(
        ProviderScope(
          overrides: [crashReporterProvider.overrideWithValue(crashReporter)],
          child: const ApmApp(),
        ),
      );
    },
    (error, stack) => crashReporter.captureError(error, stack, context: 'runZonedGuarded'),
  );
}

/// Fraunces et Inter sont bundlées (licence SIL OFL) : leurs licences
/// doivent apparaître dans le LicenseRegistry de l'app.
void _registerFontLicenses() {
  LicenseRegistry.addLicense(() async* {
    yield LicenseEntryWithLineBreaks(
      ['Fraunces'],
      await rootBundle.loadString('assets/fonts/fraunces/OFL.txt'),
    );
    yield LicenseEntryWithLineBreaks(
      ['Inter'],
      await rootBundle.loadString('assets/fonts/inter/OFL.txt'),
    );
  });
}

class ApmApp extends ConsumerWidget {
  const ApmApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);
    return MaterialApp.router(
      title: 'APM',
      // Sombre = défaut de toute l'app (DESIGN_SPEC : on parle le soir).
      // Le mode cream s'applique localement (bilan, carnet) via
      // `Theme(data: AppTheme.light(), ...)`.
      theme: AppTheme.dark(),
      routerConfig: router,
      // Wraps every routed screen (below MaterialApp's own chrome, above the
      // Navigator go_router builds) in the per-user provider scope (#373).
      builder: (context, child) => UserSessionScope(
        overrides: userScopedProviders,
        child: child ?? const SizedBox.shrink(),
      ),
    );
  }
}

/// Every provider whose state belongs to exactly ONE signed-in user (#373).
/// Listed here as a plain "self-override" — no different implementation,
/// just enough to pin each provider's instantiation to
/// [UserSessionScope]'s nested container instead of the app's root one,
/// which is what makes it subject to that container's disposal on logout.
/// `.family` providers ([proofProvider], [debriefProvider]) scope their
/// WHOLE family — every cached id — mirroring what `ref.invalidate` on a
/// family used to do.
///
/// Adding a new per-user provider means adding it HERE, the one place that
/// decides what's user-scoped, instead of ALSO writing a matching
/// `ref.invalidate` call in AuthViewModel.logout — the #373 defect: that
/// hand-maintained list could silently drift out of sync with reality the
/// day someone added a 10th per-user provider and forgot to extend it.
final List<Override> userScopedProviders = [
  profileViewModelProvider,
  streakProvider,
  progressProvider,
  reviewProvider,
  voiceConsentProvider,
  vocabularyViewModelProvider,
  proofProvider,
  debriefProvider,
  missionViewModelProvider,
];

/// Keys the per-user provider subtree to the signed-in user's id so that
/// ALL of it disappears atomically on every session change — sign-in, a
/// DIFFERENT account signing in, or sign-out — instead of relying on a
/// hand-maintained list of `ref.invalidate` calls (#373).
///
/// When [userId] changes (including to/from `null`), Flutter treats the
/// keyed [ProviderScope] below as a brand-new widget: it disposes the OLD
/// one's Element — which disposes the [ProviderContainer] it owns, tearing
/// down every provider scoped into it via [overrides] — then builds a fresh
/// container for the new id. Every provider NOT in [overrides] (auth
/// itself, network, crash reporting) keeps living in the app's root scope
/// from `main()` and is unaffected by this teardown.
///
/// [overrides] is the app's real [userScopedProviders] in production
/// ([ApmApp.build]) but is a required constructor parameter (not a default —
/// [userScopedProviders] isn't a compile-time constant) so a test can prove
/// the MECHANISM in isolation with a synthetic provider, instead of wiring
/// the whole app's dependency graph just to prove a 10th per-user provider
/// would also be reset.
class UserSessionScope extends ConsumerWidget {
  const UserSessionScope({super.key, required this.child, required this.overrides});

  final Widget child;
  final List<Override> overrides;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final userId = ref.watch(authViewModelProvider).value?.id;
    return ProviderScope(key: ValueKey(userId), overrides: overrides, child: child);
  }
}

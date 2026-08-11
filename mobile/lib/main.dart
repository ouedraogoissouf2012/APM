import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'src/core/observability/crash_reporter.dart';
import 'src/core/observability/providers.dart';
import 'src/core/router/app_router.dart';
import 'src/core/theme/app_theme.dart';

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
    );
  }
}

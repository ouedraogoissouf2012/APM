import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'crash_reporter.dart';

/// App-wide crash/error reporter (#236). Overridden in `main.dart` with the
/// SAME instance that's wired into [FlutterError.onError] and friends, so a
/// breadcrumb left by a view-model and a later unhandled crash share one
/// trail instead of two disconnected histories.
final crashReporterProvider = Provider<CrashReporter>(
  (ref) => LoggingCrashReporter(),
);

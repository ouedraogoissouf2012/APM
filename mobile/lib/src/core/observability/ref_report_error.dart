import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'providers.dart';

/// Centralizes the `if (!mounted) return; read(crashReporterProvider)...`
/// pattern that used to be copy-pasted as private `_reportError` helpers on
/// EchoViewModel and MinimalPairsViewModel (byte-identical bodies) plus ~6
/// more inline call sites across the mission/placement/vocabulary
/// view-models and proof_screen.dart (#372).
///
/// The `mounted` guard matters for an autoDispose provider's [Ref] — reading
/// ANY provider after disposal throws — but is a harmless no-op everywhere
/// else: a non-autoDispose [Ref] stays mounted for as long as its provider
/// is alive, so the guard never actually trips there.
extension RefCrashReporting on Ref {
  /// Reports [error]/[stack] to the app's crash reporter, tagged with
  /// [context] (and optional [data]) for the trail. A no-op once this [Ref]
  /// is no longer mounted, so a crash report can never itself become a crash.
  void reportError(
    Object error,
    StackTrace stack, {
    required String context,
    Map<String, Object?>? data,
  }) {
    if (!mounted) return;
    read(
      crashReporterProvider,
    ).captureError(error, stack, context: context, data: data);
  }
}

/// [WidgetRef] variant for widgets (proof_screen.dart) that have no [Ref] of
/// their own to extend.
extension WidgetRefCrashReporting on WidgetRef {
  /// See [RefCrashReporting.reportError]. Guards on [BuildContext.mounted]
  /// rather than a `Ref.mounted` ([WidgetRef] has none) — both mean the same
  /// thing here: don't touch anything once the owning widget/state has left
  /// the tree. Note: the `context` PARAMETER (the report's String label)
  /// shadows [WidgetRef.context] (the [BuildContext] getter) inside this
  /// method, hence the explicit `this.context` below.
  void reportError(
    Object error,
    StackTrace stack, {
    required String context,
    Map<String, Object?>? data,
  }) {
    if (!this.context.mounted) return;
    read(
      crashReporterProvider,
    ).captureError(error, stack, context: context, data: data);
  }
}

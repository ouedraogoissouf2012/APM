import 'dart:collection';
import 'dart:developer' as developer;

/// A single recorded event leading up to an error — the trail attached by
/// [CrashReporter.captureError], so a captured error carries the "what just
/// happened" context a bare stack trace doesn't (#236).
class Breadcrumb {
  Breadcrumb(this.message, this.time, this.data);

  final String message;
  final DateTime time;
  final Map<String, Object?>? data;

  @override
  String toString() {
    final suffix = (data == null || data!.isEmpty) ? '' : ' $data';
    return '${time.toIso8601String()} $message$suffix';
  }
}

/// Minimal mobile crash/error-reporting (#236): captures errors that would
/// otherwise vanish without a trace — genuinely unhandled crashes (wired in
/// `main.dart`) and handled-but-silent degradations that used to be a bare
/// `catch (_) {}` (e.g. a queued turn dropped on a definitive 4xx in
/// `offline_turn_sync.dart`) — each with a short trail of recent
/// [Breadcrumb]s for context.
///
/// Kept behind an interface so the sink is swappable without touching
/// callers, mirroring [VoiceTakeStore]'s seam over its storage backend.
abstract class CrashReporter {
  /// Records a lightweight trail entry — call at points worth remembering if
  /// an error happens shortly after (a network call, a definitive rejection).
  void addBreadcrumb(String message, {Map<String, Object?>? data});

  /// Records an error: a genuinely unhandled crash, or a handled failure that
  /// would otherwise vanish silently. [context] names where it happened.
  void captureError(
    Object error,
    StackTrace stackTrace, {
    String? context,
    Map<String, Object?>? data,
  });
}

/// Signature of `dart:developer`'s top-level `log()` — narrowed to what
/// [LoggingCrashReporter] uses, so a test can inject a spy without a real
/// VM service listener attached.
typedef DeveloperLog = void Function(
  String message, {
  String name,
  int level,
  Object? error,
  StackTrace? stackTrace,
});

/// Local-only [CrashReporter]: writes structured entries via `dart:developer`
/// (visible in `flutter run`, DevTools, and platform device logs) rather than
/// a third-party SaaS — no learner data leaves the device, and this class is
/// the ONE place a future remote sink would be added.
class LoggingCrashReporter implements CrashReporter {
  LoggingCrashReporter({
    int maxBreadcrumbs = 20,
    DeveloperLog? log,
    DateTime Function()? now,
  })  : _maxBreadcrumbs = maxBreadcrumbs,
        _log = log ?? developer.log,
        _now = now ?? DateTime.now;

  final int _maxBreadcrumbs;
  final DeveloperLog _log;
  final DateTime Function() _now;
  final Queue<Breadcrumb> _breadcrumbs = Queue<Breadcrumb>();

  @override
  void addBreadcrumb(String message, {Map<String, Object?>? data}) {
    _breadcrumbs.addLast(Breadcrumb(message, _now(), data));
    while (_breadcrumbs.length > _maxBreadcrumbs) {
      _breadcrumbs.removeFirst();
    }
  }

  @override
  void captureError(
    Object error,
    StackTrace stackTrace, {
    String? context,
    Map<String, Object?>? data,
  }) {
    final message = StringBuffer(context ?? 'unhandled error');
    if (data != null && data.isNotEmpty) message.write(' $data');
    if (_breadcrumbs.isNotEmpty) {
      message.write('\nbreadcrumbs: ${_breadcrumbs.join(' | ')}');
    }
    _log(
      message.toString(),
      name: 'apm.crash',
      level: 1000, // SEVERE, per dart:developer's log-level convention
      error: error,
      stackTrace: stackTrace,
    );
  }
}

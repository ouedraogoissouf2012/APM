import 'package:apm/src/core/observability/crash_reporter.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('LoggingCrashReporter', () {
    test('captureError logs the error, stack trace, and context', () {
      final logs = <Map<String, Object?>>[];
      final reporter = LoggingCrashReporter(
        log: (message, {name = '', level = 0, error, stackTrace}) => logs.add({
          'message': message,
          'name': name,
          'level': level,
          'error': error,
          'stackTrace': stackTrace,
        }),
      );
      final error = StateError('boom');
      final stack = StackTrace.current;

      reporter.captureError(error, stack, context: 'Widget.build');

      expect(logs, hasLength(1));
      expect(logs.single['message'], contains('Widget.build'));
      expect(logs.single['error'], same(error));
      expect(logs.single['stackTrace'], same(stack));
      expect(logs.single['name'], 'apm.crash');
    });

    test('captureError includes structured data in the logged message', () {
      final logs = <String>[];
      final reporter = LoggingCrashReporter(
        log: (message, {name = '', level = 0, error, stackTrace}) => logs.add(message),
      );

      reporter.captureError(
        Exception('rejected'),
        StackTrace.current,
        context: 'OfflineTurnSync.sync',
        data: {'statusCode': 422, 'idempotencyKey': 'abc-123'},
      );

      expect(logs.single, contains('statusCode'));
      expect(logs.single, contains('422'));
      expect(logs.single, contains('abc-123'));
    });

    test('breadcrumbs left before an error are attached to the capture', () {
      final logs = <String>[];
      final reporter = LoggingCrashReporter(
        log: (message, {name = '', level = 0, error, stackTrace}) => logs.add(message),
      );

      reporter.addBreadcrumb('user tapped record');
      reporter.addBreadcrumb('recording stopped', data: {'bytes': 42});
      reporter.captureError(Exception('boom'), StackTrace.current);

      expect(logs.single, contains('user tapped record'));
      expect(logs.single, contains('recording stopped'));
      expect(logs.single, contains('42'));
    });

    test('an error captured before any breadcrumb has no breadcrumb section',
        () {
      final logs = <String>[];
      final reporter = LoggingCrashReporter(
        log: (message, {name = '', level = 0, error, stackTrace}) => logs.add(message),
      );

      reporter.captureError(Exception('boom'), StackTrace.current);

      expect(logs.single, isNot(contains('breadcrumbs:')));
    });

    test('the breadcrumb trail is bounded — oldest entries drop off', () {
      final logs = <String>[];
      final reporter = LoggingCrashReporter(
        maxBreadcrumbs: 2,
        log: (message, {name = '', level = 0, error, stackTrace}) => logs.add(message),
      );

      reporter.addBreadcrumb('first');
      reporter.addBreadcrumb('second');
      reporter.addBreadcrumb('third');
      reporter.captureError(Exception('boom'), StackTrace.current);

      expect(logs.single, isNot(contains('first')));
      expect(logs.single, contains('second'));
      expect(logs.single, contains('third'));
    });
  });
}

import 'package:apm/src/core/config/app_config.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
  });

  // The API_BASE_URL --dart-define override is compile-time and cannot be
  // toggled from a test; these tests cover the dev fallbacks (no override).

  test('falls back to the Android emulator host on Android', () {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;

    expect(AppConfig.fromEnvironment.apiBaseUrl, 'http://10.0.2.2:8010');
  });

  test('falls back to localhost on non-Android local platforms', () {
    for (final platform in [
      TargetPlatform.iOS,
      TargetPlatform.macOS,
      TargetPlatform.windows,
      TargetPlatform.linux,
      TargetPlatform.fuchsia,
    ]) {
      debugDefaultTargetPlatformOverride = platform;

      expect(
        AppConfig.fromEnvironment.apiBaseUrl,
        'http://localhost:8010',
        reason: 'platform: $platform',
      );
    }
  });
}

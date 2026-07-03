import 'package:apm/src/core/config/app_config.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
  });

  test('dev config uses Android emulator host on Android', () {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;

    expect(AppConfig.devApiBaseUrl, 'http://10.0.2.2:8000');
    expect(AppConfig.dev.apiBaseUrl, 'http://10.0.2.2:8000');
  });

  test('dev config uses localhost on non-Android local platforms', () {
    for (final platform in [
      TargetPlatform.iOS,
      TargetPlatform.macOS,
      TargetPlatform.windows,
      TargetPlatform.linux,
      TargetPlatform.fuchsia,
    ]) {
      debugDefaultTargetPlatformOverride = platform;

      expect(
        AppConfig.devApiBaseUrl,
        'http://localhost:8000',
        reason: 'platform: $platform',
      );
      expect(
        AppConfig.dev.apiBaseUrl,
        'http://localhost:8000',
        reason: 'platform: $platform',
      );
    }
  });
}

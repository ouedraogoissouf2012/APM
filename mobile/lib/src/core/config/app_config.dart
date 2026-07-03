import 'package:flutter/foundation.dart';

class AppConfig {
  const AppConfig({required this.apiBaseUrl});

  /// On web/desktop/iOS simulator the backend runs at localhost:8000.
  /// Android emulators reach the host machine via 10.0.2.2.
  final String apiBaseUrl;

  static AppConfig get dev => AppConfig(apiBaseUrl: devApiBaseUrl);

  static String get devApiBaseUrl {
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }
    return 'http://localhost:8000';
  }
}

import 'package:flutter/foundation.dart';

class AppConfig {
  const AppConfig({required this.apiBaseUrl});

  /// Base URL of the APM backend API.
  final String apiBaseUrl;

  /// Product default for a new account's native language (francophone app).
  static const String defaultNativeLanguage = 'fr';

  /// Compile-time override for production/staging builds:
  ///   flutter build appbundle --dart-define=API_BASE_URL=https://api.example.com
  /// Empty when not provided, in which case the dev defaults below apply.
  static const String _apiBaseUrlOverride = String.fromEnvironment(
    'API_BASE_URL',
  );

  static AppConfig get fromEnvironment =>
      AppConfig(apiBaseUrl: _resolveApiBaseUrl());

  static String _resolveApiBaseUrl() {
    if (_apiBaseUrlOverride.isNotEmpty) return _apiBaseUrlOverride;
    // Dev defaults: on web/desktop/iOS simulator the backend runs at
    // localhost:8000; Android emulators reach the host machine via 10.0.2.2.
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }
    return 'http://localhost:8000';
  }
}

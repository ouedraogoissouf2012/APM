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
    // Dev defaults. On web, call the backend on the SAME host the page was served
    // from (localhost vs 127.0.0.1 are different origins to the browser — a
    // hardcoded host would trip CORS). Android emulators reach the host machine
    // via 10.0.2.2; other native/desktop platforms use localhost.
    if (kIsWeb) {
      final host = Uri.base.host.isEmpty ? 'localhost' : Uri.base.host;
      return 'http://$host:8000';
    }
    if (defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }
    return 'http://localhost:8000';
  }
}

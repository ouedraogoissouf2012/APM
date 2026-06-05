class AppConfig {
  const AppConfig({required this.apiBaseUrl});

  /// On web/desktop dev the backend runs at localhost:8000. Android emulators
  /// reach the host machine via 10.0.2.2.
  final String apiBaseUrl;

  static const AppConfig dev = AppConfig(apiBaseUrl: 'http://localhost:8000');
}

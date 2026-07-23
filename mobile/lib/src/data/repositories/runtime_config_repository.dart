import '../../core/network/api_client.dart';

/// Non-sensitive runtime flags fetched from the backend `/config` endpoint.
class RuntimeConfig {
  const RuntimeConfig({required this.demoMode});

  /// True when the backend runs on the fake LLM engine (no DeepSeek key): the
  /// assistant invents replies and no corrections are produced. The UI must say
  /// so instead of pretending it is really teaching.
  final bool demoMode;
}

class RuntimeConfigRepository {
  RuntimeConfigRepository(this._api);

  final ApiClient _api;

  Future<RuntimeConfig> fetch() async {
    final json = await _api.getJson('/config');
    return RuntimeConfig(demoMode: json['demo_mode'] as bool? ?? false);
  }
}

import '../../core/network/api_client.dart';

/// Non-sensitive runtime flags fetched from the backend `/config` endpoint.
class RuntimeConfig {
  const RuntimeConfig({
    required this.demoMode,
    required this.serverTts,
    this.serverStt = false,
  });

  /// True when the backend runs on the fake LLM engine (no DeepSeek key): the
  /// assistant invents replies and no corrections are produced. The UI must say
  /// so instead of pretending it is really teaching.
  final bool demoMode;

  /// True when the backend streams synthesized neural audio: the app plays that
  /// audio instead of speaking with the robotic on-device system voice.
  final bool serverTts;

  /// True when the backend transcribes recorded audio (Whisper via Groq): the
  /// app records and uploads audio instead of using the browser recognizer.
  final bool serverStt;
}

class RuntimeConfigRepository {
  RuntimeConfigRepository(this._api);

  final ApiClient _api;

  Future<RuntimeConfig> fetch() async {
    final json = await _api.getJson('/config');
    return RuntimeConfig(
      demoMode: json['demo_mode'] as bool? ?? false,
      serverTts: json['server_tts'] as bool? ?? false,
      serverStt: json['server_stt'] as bool? ?? false,
    );
  }
}

import '../../core/network/api_client.dart';

/// Non-sensitive runtime flags fetched from the backend `/config` endpoint.
class RuntimeConfig {
  const RuntimeConfig({
    required this.demoMode,
    required this.serverTts,
    this.serverStt = false,
    this.conversationServerTts = false,
    this.conversationServerStt = false,
    this.passwordResetEnabled = false,
  });

  final bool demoMode;

  /// Drills (Écho, paires, carnet): /tts is available.
  final bool serverTts;

  /// Drills: /transcribe is available.
  final bool serverStt;

  /// Conversation reply spoken on the server (Edge). Default off = Chrome voice.
  final bool conversationServerTts;

  /// Conversation listen via /transcribe. Default off = Chrome mic.
  final bool conversationServerStt;

  /// True when the backend can send reset/welcome email.
  final bool passwordResetEnabled;
}

class RuntimeConfigRepository {
  RuntimeConfigRepository(this._api);

  final ApiClient _api;

  Future<RuntimeConfig> fetch() async {
    final json = await _api.getJson('/config');
    return RuntimeConfig(
      demoMode: json['demo_mode'] as bool? ?? false,
      serverTts: json['drill_tts'] as bool? ?? json['server_tts'] as bool? ?? false,
      serverStt: json['drill_stt'] as bool? ?? json['server_stt'] as bool? ?? false,
      conversationServerTts: json['conversation_server_tts'] as bool? ?? false,
      conversationServerStt: json['conversation_server_stt'] as bool? ?? false,
      passwordResetEnabled: json['password_reset_enabled'] as bool? ?? false,
    );
  }
}

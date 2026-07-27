import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/repositories/runtime_config_repository.dart';
import '../config/app_config.dart';
import '../storage/token_storage.dart';
import 'api_client.dart';
import 'authenticated_api_client.dart';

/// Core infrastructure providers (HTTP clients, token storage).
///
/// They live in core — not inside any feature — so features depend on core
/// instead of importing each other's view models for plumbing.

final apiClientProvider = Provider<ApiClient>(
  (ref) => ApiClient(AppConfig.fromEnvironment),
);

final tokenStorageProvider = Provider<TokenStorage>(
  (ref) => SecureTokenStorage(),
);

final authenticatedApiClientProvider = Provider<AuthenticatedApiClient>(
  (ref) => AuthenticatedApiClient(
    ref.watch(apiClientProvider),
    ref.watch(tokenStorageProvider),
  ),
);

final runtimeConfigRepositoryProvider = Provider<RuntimeConfigRepository>(
  (ref) => RuntimeConfigRepository(ref.watch(apiClientProvider)),
);

/// Runtime config from the backend. Never blocks the UI: any fetch failure
/// resolves to safe defaults (real backend, on-device voice).
final runtimeConfigProvider = FutureProvider<RuntimeConfig>((ref) async {
  try {
    return await ref.watch(runtimeConfigRepositoryProvider).fetch();
  } catch (_) {
    return const RuntimeConfig(demoMode: false, serverTts: false);
  }
});

/// True when the backend is in demo mode (fake engine).
final demoModeProvider = FutureProvider<bool>((ref) async {
  return (await ref.watch(runtimeConfigProvider.future)).demoMode;
});

/// True when the backend streams neural audio (play it instead of on-device TTS).
final serverTtsProvider = FutureProvider<bool>((ref) async {
  return (await ref.watch(runtimeConfigProvider.future)).serverTts;
});

/// True when the backend transcribes audio (record & upload instead of the
/// browser recognizer).
final serverSttProvider = FutureProvider<bool>((ref) async {
  return (await ref.watch(runtimeConfigProvider.future)).serverStt;
});

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

/// True when the backend is in demo mode (fake engine). Never blocks the UI:
/// any fetch failure resolves to false (assume a real backend).
final demoModeProvider = FutureProvider<bool>((ref) async {
  try {
    final config = await ref.watch(runtimeConfigRepositoryProvider).fetch();
    return config.demoMode;
  } catch (_) {
    return false;
  }
});

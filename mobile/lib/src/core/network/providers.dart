import 'package:flutter_riverpod/flutter_riverpod.dart';

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

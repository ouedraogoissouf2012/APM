import '../storage/token_storage.dart';
import '../../data/models/auth_tokens.dart';
import 'api_client.dart';
import 'api_exception.dart';

class AuthenticatedApiClient {
  AuthenticatedApiClient(this._api, this._storage);

  final ApiClient _api;
  final TokenStorage _storage;

  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? headers,
  }) =>
      _withRefresh(
        (bearer) =>
            _api.postJson(path, body: body, bearer: bearer, headers: headers),
      );

  Future<Map<String, dynamic>> postBytes(
    String path, {
    required List<int> bytes,
    required String field,
    required String filename,
    Map<String, String>? fields,
  }) =>
      _withRefresh(
        (bearer) => _api.postBytes(
          path,
          bytes: bytes,
          field: field,
          filename: filename,
          fields: fields,
          bearer: bearer,
        ),
      );

  Future<Map<String, dynamic>> getJson(String path) =>
      _withRefresh((bearer) => _api.getJson(path, bearer: bearer));

  /// Streams response lines (SSE), refreshing the access token once if the
  /// request is rejected with a 401 before the stream starts. That 401 comes
  /// from the auth dependency (before any SSE byte), so replaying the whole
  /// request with a fresh token is safe — there is no half-consumed stream to
  /// duplicate. Without this, a long conversation whose access token expires
  /// mid-session would fail spuriously, unlike every other authenticated call.
  Stream<String> postLineStream(String path, {Map<String, dynamic>? body}) async* {
    final access = await _storage.readAccessToken();
    try {
      yield* _api.postLineStream(path, body: body, bearer: access);
    } on ApiException catch (e) {
      if (e.statusCode != 401) rethrow;
      final refreshed = await _refreshAccessToken();
      yield* _api.postLineStream(path, body: body, bearer: refreshed);
    }
  }

  Future<List<dynamic>> getList(String path) =>
      _withRefreshList((bearer) => _api.getList(path, bearer: bearer));

  Future<Map<String, dynamic>> putJson(
    String path, {
    Map<String, dynamic>? body,
  }) =>
      _withRefresh((bearer) => _api.putJson(path, body: body, bearer: bearer));

  Future<Map<String, dynamic>> patchJson(
    String path, {
    Map<String, dynamic>? body,
  }) =>
      _withRefresh((bearer) => _api.patchJson(path, body: body, bearer: bearer));

  Future<Map<String, dynamic>> deleteJson(String path) =>
      _withRefresh((bearer) => _api.deleteJson(path, bearer: bearer));

  Future<Map<String, dynamic>> _withRefresh(
    Future<Map<String, dynamic>> Function(String? bearer) request,
  ) async {
    final access = await _storage.readAccessToken();
    try {
      return await request(access);
    } on ApiException catch (e) {
      if (e.statusCode != 401) rethrow;
      final refreshedAccess = await _refreshAccessToken();
      return request(refreshedAccess);
    }
  }

  Future<List<dynamic>> _withRefreshList(
    Future<List<dynamic>> Function(String? bearer) request,
  ) async {
    final access = await _storage.readAccessToken();
    try {
      return await request(access);
    } on ApiException catch (e) {
      if (e.statusCode != 401) rethrow;
      final refreshedAccess = await _refreshAccessToken();
      return request(refreshedAccess);
    }
  }

  Future<String> _refreshAccessToken() async {
    final refresh = await _storage.readRefreshToken();
    if (refresh == null) {
      await _storage.clear();
      throw const ApiException(
        statusCode: 401,
        code: 'AuthenticationError',
        message: 'Not authenticated',
      );
    }

    try {
      final json = await _api.postJson(
        '/auth/refresh',
        body: {'refresh_token': refresh},
      );
      final tokens = AuthTokens.fromJson(json);
      await _storage.save(
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
      );
      return tokens.accessToken;
    } catch (_) {
      await _storage.clear();
      rethrow;
    }
  }
}

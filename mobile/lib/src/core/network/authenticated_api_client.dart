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
  }) =>
      _withRefresh((bearer) => _api.postJson(path, body: body, bearer: bearer));

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

  /// Streams response lines (SSE). Uses the current access token; a mid-stream
  /// 401 is not retried (the session was just validated on start), so the
  /// caller falls back to the non-streaming turn on failure.
  Stream<String> postLineStream(String path, {Map<String, dynamic>? body}) async* {
    final access = await _storage.readAccessToken();
    yield* _api.postLineStream(path, body: body, bearer: access);
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

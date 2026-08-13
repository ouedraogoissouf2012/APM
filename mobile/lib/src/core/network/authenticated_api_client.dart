import '../storage/token_storage.dart';
import '../../data/models/auth_tokens.dart';
import 'api_client.dart';
import 'api_exception.dart';
import 'token_refresher.dart';

class AuthenticatedApiClient {
  AuthenticatedApiClient(this._api, this._storage, [TokenRefresher? refresher])
    : _refresher = refresher ?? sharedTokenRefresher(_api, _storage);

  final ApiClient _api;
  final TokenStorage _storage;

  /// Every 401-triggered refresh goes through this — shared with
  /// [AuthRepository] by default (see [sharedTokenRefresher]) so the two
  /// classes collapse onto ONE single-flight `/auth/refresh` and honour the
  /// same logout coordination (#316).
  final TokenRefresher _refresher;

  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? headers,
  }) => _withRefresh(
    (bearer) =>
        _api.postJson(path, body: body, bearer: bearer, headers: headers),
  );

  Future<Map<String, dynamic>> postBytes(
    String path, {
    required List<int> bytes,
    required String field,
    required String filename,
    Map<String, String>? fields,
  }) => _withRefresh(
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
  /// The refresh goes through [_refreshAccessToken], so it shares the same
  /// single-flight lock as the JSON verbs — a stream 401 racing a JSON 401
  /// still rotates the refresh token only once.
  Stream<String> postLineStream(
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? headers,
  }) async* {
    final access = await _storage.readAccessToken();
    try {
      yield* _api.postLineStream(
        path,
        body: body,
        bearer: access,
        headers: headers,
      );
    } on ApiException catch (e) {
      if (e.statusCode != 401) rethrow;
      final refreshed = await _refreshAccessToken();
      yield* _api.postLineStream(
        path,
        body: body,
        bearer: refreshed,
        headers: headers,
      );
    }
  }

  Future<List<dynamic>> getList(String path) => _withRefresh<List<dynamic>>(
    (bearer) => _api.getList(path, bearer: bearer),
  );

  Future<Map<String, dynamic>> putJson(
    String path, {
    Map<String, dynamic>? body,
  }) =>
      _withRefresh((bearer) => _api.putJson(path, body: body, bearer: bearer));

  Future<Map<String, dynamic>> patchJson(
    String path, {
    Map<String, dynamic>? body,
  }) => _withRefresh(
    (bearer) => _api.patchJson(path, body: body, bearer: bearer),
  );

  Future<Map<String, dynamic>> deleteJson(String path) =>
      _withRefresh((bearer) => _api.deleteJson(path, bearer: bearer));

  /// Runs [request] with the current access token, and on a single 401 refreshes
  /// the token once and retries. Generic over the response shape so JSON-object,
  /// JSON-list and multipart verbs share one implementation (was duplicated).
  Future<T> _withRefresh<T>(Future<T> Function(String? bearer) request) async {
    final access = await _storage.readAccessToken();
    try {
      return await request(access);
    } on ApiException catch (e) {
      if (e.statusCode != 401) rethrow;
      final refreshedAccess = await _refreshAccessToken();
      return request(refreshedAccess);
    }
  }

  /// Refreshes the access token via the shared [TokenRefresher] (single-flight
  /// + logout coordination live there, see #316) and returns the new access
  /// token for the caller's retry.
  Future<String> _refreshAccessToken() async {
    final json = await _refresher.refresh();
    return AuthTokens.fromJson(json).accessToken;
  }
}

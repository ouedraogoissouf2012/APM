import '../storage/token_storage.dart';
import '../../data/models/auth_tokens.dart';
import 'api_client.dart';
import 'api_exception.dart';

class AuthenticatedApiClient {
  AuthenticatedApiClient(this._api, this._storage);

  final ApiClient _api;
  final TokenStorage _storage;

  /// The refresh currently in flight, if any. Every 401-triggered refresh goes
  /// through [_refreshAccessToken], which shares this single Future across all
  /// concurrent callers (single-flight) — see that method for why.
  Future<String>? _refreshInFlight;

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
      yield* _api.postLineStream(path, body: body, bearer: access, headers: headers);
    } on ApiException catch (e) {
      if (e.statusCode != 401) rethrow;
      final refreshed = await _refreshAccessToken();
      yield* _api.postLineStream(path, body: body, bearer: refreshed, headers: headers);
    }
  }

  Future<List<dynamic>> getList(String path) =>
      _withRefresh<List<dynamic>>((bearer) => _api.getList(path, bearer: bearer));

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

  /// Runs [request] with the current access token, and on a single 401 refreshes
  /// the token once and retries. Generic over the response shape so JSON-object,
  /// JSON-list and multipart verbs share one implementation (was duplicated).
  Future<T> _withRefresh<T>(
    Future<T> Function(String? bearer) request,
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

  /// Refreshes the access token, collapsing concurrent callers onto a single
  /// in-flight refresh (single-flight).
  ///
  /// The backend rotates refresh tokens as single-use under a row lock, so two
  /// independent refreshes racing on the same 401 (e.g. several requests fired
  /// after the app resumes with an expired access token) would POST the *same*
  /// refresh token twice: the first rotates it, the second hits an already-used
  /// token, gets a 401, and [_performRefresh] then wipes still-valid tokens — a
  /// phantom logout. Sharing one Future guarantees exactly one POST /auth/refresh
  /// per rotation. A caller arriving after the in-flight refresh settles reads
  /// the freshly rotated token from storage and rotates again legitimately.
  ///
  /// The body is synchronous (no `await` before the assignment) so two callers
  /// on the same event-loop turn observe the memoised Future rather than each
  /// starting their own.
  Future<String> _refreshAccessToken() {
    return _refreshInFlight ??=
        _performRefresh().whenComplete(() => _refreshInFlight = null);
  }

  Future<String> _performRefresh() async {
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

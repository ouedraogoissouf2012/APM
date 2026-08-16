import '../../data/models/auth_tokens.dart';
import '../storage/token_storage.dart';
import 'api_client.dart';
import 'api_exception.dart';

/// Owns the ONE `/auth/refresh` flow shared by [AuthRepository] (explicit
/// refresh, e.g. on startup) and [AuthenticatedApiClient] (401-triggered
/// refresh on any authenticated call) — merging what used to be two
/// independent, duplicated implementations (#316).
///
/// Two guarantees:
///  - Single-flight: concurrent callers collapse onto ONE `POST /auth/refresh`.
///    The backend rotates refresh tokens as single-use under a row lock, so two
///    independent refreshes racing on the same token would burn it twice: the
///    first rotates it, the second hits an already-used token and 401s.
///  - Logout coordination (#316): [invalidateAndClear] and a refresh's
///    read-token-and-snapshot-generation step run under a shared internal
///    lock, so they can never interleave — whichever reaches its critical
///    section first fully finishes before the other's runs. That lock has to
///    guard the READ, not just the later save: a bare "has the generation
///    changed since I started" check, compared only at save time, is NOT
///    enough on its own — a refresh that starts reading DURING
///    [invalidateAndClear] (after its generation bump but before its
///    `storage.clear()` actually finishes) would still see the OLD, not-yet-
///    cleared token and capture the ALREADY-bumped generation as its own
///    baseline, so a later "did the generation change since MY start" check
///    would find no mismatch and save anyway. Locking the read forces it to
///    happen strictly before or strictly after [invalidateAndClear] — never
///    "during" — so it either gets a valid token with the OLD generation (a
///    later mismatch check then correctly catches it) or gets `null` because
///    storage is already cleared (the existing not-authenticated path).
class TokenRefresher {
  TokenRefresher(this._api, this._storage);

  final ApiClient _api;
  final TokenStorage _storage;

  int _generation = 0;
  Future<Map<String, dynamic>>? _inFlight;

  // Serializes `invalidateAndClear()` against a refresh's generation-check +
  // save. Each call chains onto whatever's currently queued, so entries run
  // strictly one at a time, in arrival order — a minimal async mutex (no
  // extra package: `synchronized` is only a transitive dependency here, not
  // one this app declares).
  Future<void> _mutex = Future.value();

  Future<T> _exclusive<T>(Future<T> Function() action) {
    final result = _mutex.then((_) => action());
    // Keep the queue alive even if `action` throws — a REJECTED `_mutex`
    // would permanently wedge every later call. `result` (returned below)
    // still carries the real outcome for THIS caller.
    _mutex = result.then((_) {}, onError: (_) {});
    return result;
  }

  /// Called by [AuthRepository.logout]: invalidates any refresh (in flight,
  /// or that starts before this finishes) and clears storage, as ONE
  /// uninterruptible step relative to a refresh's own save — see the class
  /// doc for why a plain generation bump alone can't guarantee this.
  Future<void> invalidateAndClear() {
    return _exclusive(() async {
      _generation++;
      await _storage.clear();
    });
  }

  /// Refreshes the access/refresh tokens and returns the raw response JSON.
  /// Callers extract what they need: [AuthenticatedApiClient] only wants the
  /// access token, [AuthRepository] also wants the `user` field.
  Future<Map<String, dynamic>> refresh() {
    // Synchronous (no `await` before the assignment): two callers on the same
    // event-loop turn observe the memoised Future rather than each starting
    // their own.
    return _inFlight ??= _performRefresh().whenComplete(() => _inFlight = null);
  }

  Future<Map<String, dynamic>> _performRefresh() async {
    // Locked (#316, see class doc): the token read and the generation
    // snapshot must happen as ONE step relative to invalidateAndClear(), or
    // this refresh could read a token that's about to be invalidated without
    // ever observing the generation bump that would flag it as stale.
    final (:generation, :refreshToken) = await _exclusive(
      () async => (
        generation: _generation,
        refreshToken: await _storage.readRefreshToken(),
      ),
    );
    if (refreshToken == null) {
      throw const ApiException(
        statusCode: 401,
        code: 'AuthenticationError',
        message: 'Not authenticated',
      );
    }

    final Map<String, dynamic> json;
    try {
      json = await _api.postJson(
        '/auth/refresh',
        body: {'refresh_token': refreshToken},
      );
    } catch (e) {
      // #315: a network hiccup must not wipe still-valid tokens — only a
      // definitive rejection (401: the refresh token itself is invalid or
      // already used) means the session is actually over.
      if (e is ApiException && e.statusCode == 401) {
        // #423: only wipe if THIS refresh still owns the session. Logout +
        // login B bumps _generation; clearing here would delete B's tokens.
        await _exclusive(() async {
          if (_generation == generation) {
            await _storage.clear();
          }
        });
      }
      rethrow;
    }

    return _exclusive(() async {
      if (_generation != generation) {
        // #316: logout() ran (or is running) — see class doc. The backend DID
        // rotate the token, but persisting it now would resurrect a session
        // the user explicitly ended — treat it the same as any auth failure.
        throw const ApiException(
          statusCode: 401,
          code: 'AuthenticationError',
          message: 'Session ended',
        );
      }
      final tokens = AuthTokens.fromJson(json);
      await _storage.save(
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
      );
      return json;
    });
  }
}

import 'dart:convert';

import 'package:dio/dio.dart';

import '../config/app_config.dart';
import 'api_exception.dart';

class ApiClient {
  ApiClient(AppConfig config, {Dio? dio})
    : _dio =
          dio ??
          Dio(
            BaseOptions(
              baseUrl: config.apiBaseUrl,
              // #317: without these, a request whose TCP connection is accepted
              // but never answered (captive portal, a cellular network that
              // blackholes the socket) hangs forever — no DioException is ever
              // thrown, so the offline/error path never triggers and the UI is
              // stuck "thinking" indefinitely. `receiveTimeout` resets on every
              // received byte (not the total response duration), so it doesn't
              // cut off a normal SSE turn stream mid-flight — only a truly dead
              // connection with no bytes at all for the whole window trips it.
              connectTimeout: const Duration(seconds: 10),
              sendTimeout: const Duration(seconds: 15),
              receiveTimeout: const Duration(seconds: 30),
            ),
          );

  final Dio _dio;

  Dio get raw => _dio;

  /// POSTs raw bytes as a multipart file field (used to upload recorded audio to
  /// /transcribe). Optional [fields] add plain text form fields alongside the
  /// file — e.g. the target phrase for /shadowing/attempt.
  Future<Map<String, dynamic>> postBytes(
    String path, {
    required List<int> bytes,
    required String field,
    required String filename,
    Map<String, String>? fields,
    String? bearer,
  }) async {
    try {
      final form = FormData.fromMap({
        ...?fields,
        field: MultipartFile.fromBytes(bytes, filename: filename),
      });
      final response = await _dio.post<Map<String, dynamic>>(
        path,
        data: form,
        // A longer, dedicated sendTimeout (#317): Dio's send timer is a flat
        // wall-clock cap on the WHOLE upload, never reset by progress — the
        // 15s default (fine for a small JSON body) would abort a still-healthy
        // multi-MB audio upload (recordings run up to 4 MB, see
        // AudioRecordingService._defaultMaxBytes) on a slow connection well
        // before it could finish.
        options: _options(bearer, sendTimeout: const Duration(seconds: 60)),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    String? bearer,
    Map<String, String>? headers,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        path,
        data: body,
        options: _options(bearer, extra: headers),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  Future<Map<String, dynamic>> getJson(String path, {String? bearer}) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        path,
        options: _options(bearer),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  Future<List<dynamic>> getList(String path, {String? bearer}) async {
    try {
      final response = await _dio.get<List<dynamic>>(
        path,
        options: _options(bearer),
      );
      return response.data ?? <dynamic>[];
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  Future<Map<String, dynamic>> putJson(
    String path, {
    Map<String, dynamic>? body,
    String? bearer,
  }) async {
    try {
      final response = await _dio.put<Map<String, dynamic>>(
        path,
        data: body,
        options: _options(bearer),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  Future<Map<String, dynamic>> patchJson(
    String path, {
    Map<String, dynamic>? body,
    String? bearer,
  }) async {
    try {
      final response = await _dio.patch<Map<String, dynamic>>(
        path,
        data: body,
        options: _options(bearer),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  Future<Map<String, dynamic>> deleteJson(String path, {String? bearer}) async {
    try {
      final response = await _dio.delete<Map<String, dynamic>>(
        path,
        options: _options(bearer),
      );
      return response.data ?? <String, dynamic>{};
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  /// POSTs and streams the response body as decoded text lines — used for the
  /// Server-Sent Events turn endpoint. The line stream is fed to [parseSse].
  Stream<String> postLineStream(
    String path, {
    Map<String, dynamic>? body,
    String? bearer,
    Map<String, String>? headers,
  }) async* {
    final Response<ResponseBody> response;
    try {
      response = await _dio.post<ResponseBody>(
        path,
        data: body,
        // Same header logic as the JSON verbs (bearer + custom headers, e.g. an
        // Idempotency-Key) — shared via _headers so streaming can't silently drop
        // a header the non-streaming path sends.
        //
        // A much longer, dedicated receiveTimeout (#317): the backend
        // deliberately never times out a reply already in progress (see
        // turn_service.py/fallback.py — "never abort a reply in progress"),
        // and Dio's receive timer resets on every SSE byte but NOT across a
        // silent gap between sentences while the LLM is still generating. The
        // global 30s default (right for an ordinary JSON call) would kill a
        // legitimately slow-but-healthy conversation turn. Still finite —
        // #317's actual concern (a connection that answers NOTHING, ever)
        // trips this well before 2 minutes, since receiveTimeout also covers
        // the wait for the very first byte.
        options: Options(
          responseType: ResponseType.stream,
          headers: _headers(bearer, headers),
          receiveTimeout: const Duration(minutes: 2),
        ),
      );
    } on DioException catch (e) {
      throw _toApiException(e);
    }
    final byteStream = response.data!.stream.map((chunk) => chunk.toList());
    yield* byteStream.transform(utf8.decoder).transform(const LineSplitter());
  }

  Map<String, String> _headers(String? bearer, [Map<String, String>? extra]) =>
      {if (bearer != null) 'Authorization': 'Bearer $bearer', ...?extra};

  Options _options(
    String? bearer, {
    Map<String, String>? extra,
    Duration? sendTimeout,
  }) => Options(headers: _headers(bearer, extra), sendTimeout: sendTimeout);

  ApiException _toApiException(DioException e) {
    final status = e.response?.statusCode ?? 0;
    final data = e.response?.data;
    if (data is Map && data['error'] is Map) {
      final err = data['error'] as Map;
      return ApiException(
        statusCode: status,
        code: (err['code'] ?? 'error').toString(),
        message: (err['message'] ?? 'Request failed').toString(),
      );
    }
    return ApiException(
      statusCode: status,
      code: 'network',
      message: e.message ?? 'Network error',
    );
  }
}

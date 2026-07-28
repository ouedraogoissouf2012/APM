import 'dart:convert';

import 'package:dio/dio.dart';

import '../config/app_config.dart';
import 'api_exception.dart';

class ApiClient {
  ApiClient(AppConfig config, {Dio? dio})
    : _dio = dio ?? Dio(BaseOptions(baseUrl: config.apiBaseUrl));

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
        options: _options(bearer),
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
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        path,
        data: body,
        options: _options(bearer),
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

  /// POSTs and streams the response body as decoded text lines — used for the
  /// Server-Sent Events turn endpoint. The line stream is fed to [parseSse].
  Stream<String> postLineStream(
    String path, {
    Map<String, dynamic>? body,
    String? bearer,
  }) async* {
    final Response<ResponseBody> response;
    try {
      response = await _dio.post<ResponseBody>(
        path,
        data: body,
        options: Options(
          responseType: ResponseType.stream,
          headers: bearer == null ? null : {'Authorization': 'Bearer $bearer'},
        ),
      );
    } on DioException catch (e) {
      throw _toApiException(e);
    }
    final byteStream = response.data!.stream.map((chunk) => chunk.toList());
    yield* byteStream.transform(utf8.decoder).transform(const LineSplitter());
  }

  Options _options(String? bearer) => Options(
    headers: bearer == null ? null : {'Authorization': 'Bearer $bearer'},
  );

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

import 'package:dio/dio.dart';

import '../config/app_config.dart';
import 'api_exception.dart';

class ApiClient {
  ApiClient(AppConfig config, {Dio? dio})
      : _dio = dio ?? Dio(BaseOptions(baseUrl: config.apiBaseUrl));

  final Dio _dio;

  Dio get raw => _dio;

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
      final response = await _dio.get<Map<String, dynamic>>(path, options: _options(bearer));
      return response.data ?? <String, dynamic>{};
    } on DioException catch (e) {
      throw _toApiException(e);
    }
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
    return ApiException(statusCode: status, code: 'network', message: e.message ?? 'Network error');
  }
}

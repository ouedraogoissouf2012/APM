/// A normalized API error. The backend returns `{ "error": { "code", "message" } }`.
class ApiException implements Exception {
  const ApiException({required this.statusCode, required this.code, required this.message});

  final int statusCode;
  final String code;
  final String message;

  @override
  String toString() => 'ApiException($statusCode, $code): $message';
}

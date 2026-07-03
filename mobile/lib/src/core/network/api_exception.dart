/// A normalized API error. The backend returns `{ "error": { "code", "message" } }`.
class ApiException implements Exception {
  const ApiException({
    required this.statusCode,
    required this.code,
    required this.message,
  });

  final int statusCode;
  final String code;
  final String message;

  @override
  String toString() => 'ApiException($statusCode, $code): ${_redact(message)}';
}

String _redact(String value) {
  var redacted = value.replaceAll(
    RegExp(r'Bearer\s+[A-Za-z0-9._~+/=-]+', caseSensitive: false),
    'Bearer [redacted]',
  );
  redacted = redacted.replaceAll(
    RegExp(
      r'(access[_ -]?token|refresh[_ -]?token)\s*[:=]\s*[A-Za-z0-9._~+/=-]+',
      caseSensitive: false,
    ),
    r'$1=[redacted]',
  );
  return redacted;
}

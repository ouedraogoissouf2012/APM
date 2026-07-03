import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/data/models/auth_tokens.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('AuthTokens.toString redacts token values', () {
    const tokens = AuthTokens(
      accessToken: 'access.secret.value',
      refreshToken: 'refresh-secret-value',
    );

    final rendered = tokens.toString();

    expect(rendered, contains('[redacted]'));
    expect(rendered, isNot(contains('access.secret.value')));
    expect(rendered, isNot(contains('refresh-secret-value')));
  });

  test('ApiException.toString redacts bearer and named tokens', () {
    const error = ApiException(
      statusCode: 401,
      code: 'AuthenticationError',
      message:
          'Bearer access.secret.value refresh_token=refresh-secret-value access token: abc123',
    );

    final rendered = error.toString();

    expect(rendered, contains('Bearer [redacted]'));
    expect(rendered, isNot(contains('access.secret.value')));
    expect(rendered, isNot(contains('refresh-secret-value')));
    expect(rendered, isNot(contains('abc123')));
  });
}

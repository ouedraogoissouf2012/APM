import 'dart:io';

import 'package:apm/src/core/config/app_config.dart';
import 'package:apm/src/core/network/api_client.dart';
import 'package:apm/src/core/network/api_exception.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('#317 — timeouts', () {
    test('the default Dio instance has sane connect/send/receive timeouts', () {
      final client = ApiClient(
        const AppConfig(apiBaseUrl: 'http://example.invalid'),
      );

      final options = client.raw.options;
      expect(options.connectTimeout, isNotNull);
      expect(options.sendTimeout, isNotNull);
      expect(options.receiveTimeout, isNotNull);
      // Bounded on the high side too — a "timeout" of e.g. 10 minutes would
      // technically satisfy "not null" while leaving the UI stuck just as long
      // as no timeout at all for any realistic captive-portal/dead-socket case.
      expect(
        options.connectTimeout!,
        lessThanOrEqualTo(const Duration(seconds: 30)),
      );
      expect(
        options.sendTimeout!,
        lessThanOrEqualTo(const Duration(seconds: 30)),
      );
      expect(
        options.receiveTimeout!,
        lessThanOrEqualTo(const Duration(seconds: 60)),
      );
    });

    test('a request whose server accepts the TCP connection but never answers '
        'fails with an ApiException instead of hanging forever', () async {
      // Simulates the exact bug #317 describes (captive portal, a cellular
      // network that blackholes the socket): a REAL server that accepts the
      // connection and then never writes a single byte back. Uses its own
      // short timeouts (300ms) via the `dio:` injection seam rather than the
      // production ApiClient(config) defaults (10s/15s/30s, asserted above) —
      // same mechanism (BaseOptions timeouts), just fast enough for a unit
      // test instead of taking 10-30 real seconds per run.
      final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(server.close);
      server.listen((socket) {
        socket.listen((_) {}); // drain the request, answer nothing, ever
      });

      final dio = Dio(
        BaseOptions(
          baseUrl: 'http://${server.address.address}:${server.port}',
          connectTimeout: const Duration(milliseconds: 300),
          receiveTimeout: const Duration(milliseconds: 300),
        ),
      );
      final client = ApiClient(const AppConfig(apiBaseUrl: ''), dio: dio);

      await expectLater(
        client.getJson('/ping').timeout(const Duration(seconds: 5)),
        throwsA(isA<ApiException>()),
      );
    });

    test(
      'postBytes overrides the global sendTimeout with a longer one, so a '
      'slow-but-healthy audio upload is not cut off by the JSON-call default',
      () async {
        Duration? capturedSendTimeout;
        final dio = Dio(
          BaseOptions(
            baseUrl: 'http://example.invalid',
            // The default JSON-call sendTimeout is short — postBytes must NOT
            // inherit it for a multi-MB upload.
            sendTimeout: const Duration(seconds: 1),
          ),
        );
        dio.interceptors.add(
          InterceptorsWrapper(
            onRequest: (options, handler) {
              capturedSendTimeout = options.sendTimeout;
              // Short-circuit before any real I/O — this test only cares what
              // timeout got resolved onto the request, not the network result.
              handler.reject(
                DioException(
                  requestOptions: options,
                  type: DioExceptionType.cancel,
                ),
              );
            },
          ),
        );
        final client = ApiClient(const AppConfig(apiBaseUrl: ''), dio: dio);

        await expectLater(
          client.postBytes(
            '/transcribe',
            bytes: const [1, 2, 3],
            field: 'audio',
            filename: 'a.wav',
          ),
          throwsA(isA<ApiException>()),
        );
        expect(capturedSendTimeout, const Duration(seconds: 60));
      },
    );

    test(
      'postLineStream overrides the global receiveTimeout with a much longer '
      'one, so a legitimately slow (not dead) conversation turn is not cut off',
      () async {
        Duration? capturedReceiveTimeout;
        final dio = Dio(
          BaseOptions(
            baseUrl: 'http://example.invalid',
            receiveTimeout: const Duration(seconds: 1),
          ),
        );
        dio.interceptors.add(
          InterceptorsWrapper(
            onRequest: (options, handler) {
              capturedReceiveTimeout = options.receiveTimeout;
              handler.reject(
                DioException(
                  requestOptions: options,
                  type: DioExceptionType.cancel,
                ),
              );
            },
          ),
        );
        final client = ApiClient(const AppConfig(apiBaseUrl: ''), dio: dio);

        await expectLater(
          client
              .postLineStream('/sessions/1/turn/stream', body: const {})
              .toList(),
          throwsA(isA<ApiException>()),
        );
        expect(capturedReceiveTimeout, const Duration(minutes: 2));
      },
    );
  });
}

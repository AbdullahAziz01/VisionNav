import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:visionnav_app/services/backend_config.dart';
import 'package:visionnav_app/services/visionnav_api.dart';

void main() {
  group('BackendConfig URL & Environment Tests', () {
    test('Development allows HTTP and HTTPS URLs', () {
      expect(
        BackendConfig.validateUrl(
          'http://192.168.1.50:8000',
          BackendEnvironment.development,
        ),
        isNull,
      );
      expect(
        BackendConfig.validateUrl(
          'https://api.visionnav.example.com',
          BackendEnvironment.development,
        ),
        isNull,
      );
    });

    test('Production strictly requires HTTPS and rejects HTTP', () {
      final err = BackendConfig.validateUrl(
        'http://api.visionnav.example.com',
        BackendEnvironment.production,
      );
      expect(err, isNotNull);
      expect(err, contains('HTTPS'));

      expect(
        BackendConfig.validateUrl(
          'https://api.visionnav.example.com',
          BackendEnvironment.production,
        ),
        isNull,
      );
    });

    test('Production config throws ArgumentError when passed http:// URL', () {
      expect(
        () => BackendConfig(
          environment: BackendEnvironment.production,
          baseUrl: 'http://insecure.visionnav.com',
        ),
        throwsArgumentError,
      );
    });

    test('Http client rejects an HTTP override in production', () {
      final config = BackendConfig(
        environment: BackendEnvironment.production,
        baseUrl: 'https://api.visionnav.example.com',
      );
      expect(
        () => HttpVisionNavApi(
          config: config,
          baseUrl: 'http://insecure.visionnav.example.com',
          client: MockClient((_) async => http.Response('{}', 200)),
        ),
        throwsArgumentError,
      );
    });

    test('Session ID generation and reset works', () {
      final config = BackendConfig(
        environment: BackendEnvironment.development,
        baseUrl: 'http://localhost:8000',
      );
      final initialId = config.sessionId;
      expect(initialId.startsWith('phone-'), isTrue);

      final newId = config.resetSessionId();
      expect(newId.startsWith('phone-'), isTrue);
      expect(newId, isNot(equals(initialId)));
      expect(config.sessionId, equals(newId));
    });
  });

  group('HttpVisionNavApi Client Tests', () {
    test('Outgoing requests send X-Session-ID and X-API-Key headers', () async {
      final config = BackendConfig(
        environment: BackendEnvironment.development,
        baseUrl: 'http://localhost:8000',
        apiKey: 'test-api-secret',
        sessionId: 'test-session-42',
      );

      final mockClient = MockClient((request) async {
        expect(request.headers['X-Session-ID'], equals('test-session-42'));
        expect(request.headers['X-API-Key'], equals('test-api-secret'));

        if (request.url.path == '/ready') {
          return http.Response(
            jsonEncode({
              'status': 'ready',
              'api': 'ok',
              'yolo_model': 'yolov8n.pt',
              'mono_depth_backend': 'depth_anything_v2',
            }),
            200,
          );
        }
        return http.Response('Not Found', 404);
      });

      final api = HttpVisionNavApi(config: config, client: mockClient);
      await api.connect();
      expect(api.isConnected, isTrue);
      api.dispose();
    });

    test('Handles 409 Session Conflict exception', () async {
      final config = BackendConfig(
        environment: BackendEnvironment.development,
        baseUrl: 'http://localhost:8000',
      );

      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'Another phone session is active'}),
          409,
        );
      });

      final api = HttpVisionNavApi(config: config, client: mockClient);
      expect(
        () => api.acquireSession(),
        throwsA(isA<SessionConflictException>()),
      );
      api.dispose();
    });

    test('Handles 401 Authentication Failed exception', () async {
      final config = BackendConfig(
        environment: BackendEnvironment.development,
        baseUrl: 'http://localhost:8000',
      );

      final mockClient = MockClient((request) async {
        return http.Response(jsonEncode({'detail': 'Invalid API Key'}), 401);
      });

      final api = HttpVisionNavApi(config: config, client: mockClient);
      expect(() => api.connect(), throwsA(isA<BackendAuthException>()));
      api.dispose();
    });

    test(
      'Acquires and releases the snapshotted session with auth headers',
      () async {
        final config = BackendConfig(
          environment: BackendEnvironment.development,
          baseUrl: 'http://localhost:8000',
          apiKey: 'api-secret',
          sessionId: 'session-before-pause',
        );
        final requests = <http.BaseRequest>[];
        final mockClient = MockClient((request) async {
          requests.add(request);
          expect(request.headers['X-API-Key'], 'api-secret');
          if (request.url.path == '/session/acquire') {
            final payload = jsonDecode(request.body) as Map<String, dynamic>;
            expect(payload['session_id'], 'session-before-pause');
            expect(payload['force'], isFalse);
            expect(request.headers['X-Session-ID'], 'session-before-pause');
            return http.Response(
              jsonEncode({'session_id': payload['session_id']}),
              200,
            );
          }
          final payload = jsonDecode(request.body) as Map<String, dynamic>;
          expect(payload['session_id'], 'session-before-pause');
          expect(request.headers['X-Session-ID'], 'session-before-pause');
          return http.Response('{}', 200);
        });
        final api = HttpVisionNavApi(config: config, client: mockClient);

        await api.acquireSession();
        config.resetSessionId();
        await api.releaseSession(sessionId: 'session-before-pause');

        expect(requests.map((request) => request.url.path), [
          '/session/acquire',
          '/session/release',
        ]);
        api.dispose();
      },
    );

    test(
      'Maps frame responses and sends credentials on multipart request',
      () async {
        final config = BackendConfig(
          environment: BackendEnvironment.development,
          baseUrl: 'http://localhost:8000',
          apiKey: 'frame-secret',
          sessionId: 'frame-session',
        );
        final result = <Map<String, dynamic>>[];
        final api = HttpVisionNavApi(
          config: config,
          client: MockClient((request) async {
            expect(request.url.path, '/pipeline/frame');
            expect(request.method, 'POST');
            expect(request.headers['X-API-Key'], 'frame-secret');
            expect(request.headers['X-Session-ID'], 'frame-session');
            expect(
              request.headers['content-type'],
              startsWith('multipart/form-data'),
            );
            return http.Response(jsonEncode({'frame_index': 7}), 200);
          }),
        );
        final subscription = api.resultsStream.listen(result.add);

        await api.sendFrame([1, 2, 3]);
        await Future<void>.delayed(Duration.zero);

        expect(result, [
          {'frame_index': 7},
        ]);
        await subscription.cancel();
        api.dispose();
      },
    );

    test(
      'Does not publish a frame result after lifecycle invalidation',
      () async {
        final response = Completer<http.Response>();
        final api = HttpVisionNavApi(
          config: BackendConfig(
            environment: BackendEnvironment.development,
            baseUrl: 'http://localhost:8000',
          ),
          client: MockClient((_) => response.future),
        );
        final results = <Map<String, dynamic>>[];
        final subscription = api.resultsStream.listen(results.add);
        final pendingSend = api.sendFrame([1, 2, 3]);
        await Future<void>.delayed(Duration.zero);

        api.invalidatePendingOperations();
        response.complete(http.Response(jsonEncode({'frame_index': 99}), 200));
        await pendingSend;
        await Future<void>.delayed(Duration.zero);

        expect(api.isConnected, isFalse);
        expect(results, isEmpty);
        await subscription.cancel();
        api.dispose();
      },
    );

    test(
      'HTTP 503 is backend unavailable, not a network retry failure',
      () async {
        final api = HttpVisionNavApi(
          config: BackendConfig(
            environment: BackendEnvironment.development,
            baseUrl: 'http://localhost:8000',
          ),
          client: MockClient(
            (_) async => http.Response(
              jsonEncode({'detail': 'Service initializing'}),
              503,
            ),
          ),
        );

        await expectLater(
          api.connect(),
          throwsA(isA<BackendUnavailableException>()),
        );
        expect(api.isConnected, isFalse);
        api.dispose();
      },
    );

    test(
      'Maps frame HTTP 401, 409, 413, and 503 without retry typing',
      () async {
        final cases = <(int, Type)>[
          (401, BackendAuthException),
          (409, SessionConflictException),
          (413, PayloadTooLargeException),
          (503, BackendUnavailableException),
        ];

        for (final (status, errorType) in cases) {
          final api = HttpVisionNavApi(
            config: BackendConfig(
              environment: BackendEnvironment.development,
              baseUrl: 'http://localhost:8000',
            ),
            client: MockClient(
              (_) async => http.Response(
                jsonEncode({'detail': 'status $status'}),
                status,
              ),
            ),
          );
          await expectLater(
            api.sendFrame([1, 2, 3]),
            throwsA(
              isA<Exception>().having(
                (error) => error.runtimeType,
                'runtimeType',
                errorType,
              ),
            ),
          );
          expect(api.isConnected, isFalse);
          api.dispose();
        }
      },
    );

    test('Classifies mocked transport errors for network-only retry', () async {
      final api = HttpVisionNavApi(
        config: BackendConfig(
          environment: BackendEnvironment.development,
          baseUrl: 'http://localhost:8000',
        ),
        client: MockClient((_) async => throw http.ClientException('offline')),
      );

      await expectLater(api.connect(), throwsA(isA<BackendNetworkException>()));
      expect(api.isConnected, isFalse);
      api.dispose();
    });
  });
}

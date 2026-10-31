import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:visionnav_app/services/backend_config.dart';
import 'package:visionnav_app/services/service_interfaces.dart';

/// Legacy compile-time fallback constant (kept for backwards compatibility).
const String kVisionNavApiBaseUrl = String.fromEnvironment(
  'VISIONNAV_API_URL',
  defaultValue: 'http://127.0.0.1:8000',
);

class SessionConflictException implements Exception {
  SessionConflictException(this.message);
  final String message;
  @override
  String toString() => message;
}

class BackendAuthException implements Exception {
  BackendAuthException(this.message);
  final String message;
  @override
  String toString() => message;
}

class PayloadTooLargeException implements Exception {
  PayloadTooLargeException(this.message);
  final String message;
  @override
  String toString() => message;
}

class BackendUnavailableException implements Exception {
  BackendUnavailableException(this.message);
  final String message;
  @override
  String toString() => message;
}

class BackendHttpException implements Exception {
  BackendHttpException(this.statusCode, this.message);
  final int statusCode;
  final String message;
  @override
  String toString() => message;
}

class BackendNetworkException implements Exception {
  BackendNetworkException(this.message, [this.cause]);
  final String message;
  final Object? cause;
  @override
  String toString() => message;
}

class HttpVisionNavApi implements VisionNavApi {
  HttpVisionNavApi({
    BackendConfig? config,
    String? baseUrl,
    http.Client? client,
  }) : _config = config ?? BackendConfig.instance,
       _client = client ?? http.Client(),
       _explicitBaseUrl = baseUrl {
    _validateBaseUrl();
  }

  final BackendConfig _config;
  final http.Client _client;
  final String? _explicitBaseUrl;
  final StreamController<Map<String, dynamic>> _results =
      StreamController<Map<String, dynamic>>.broadcast();

  bool _connected = false;
  int _requestEpoch = 0;

  bool get isConnected => _connected;
  String get baseUrl {
    _validateBaseUrl();
    return _explicitBaseUrl ?? _config.baseUrl;
  }

  BackendConfig get config => _config;

  void _validateBaseUrl() {
    final error = BackendConfig.validateUrl(
      _explicitBaseUrl ?? _config.baseUrl,
      _config.environment,
    );
    if (error != null) throw ArgumentError(error);
  }

  Map<String, String> _headersForSession(String sessionId) {
    final headers = <String, String>{'X-Session-ID': sessionId};
    if (_config.apiKey.isNotEmpty) {
      headers['X-API-Key'] = _config.apiKey;
    }
    return headers;
  }

  Map<String, String> get _authAndSessionHeaders =>
      _headersForSession(_config.sessionId);

  Future<T> _networkRequest<T>(Future<T> Function() request) async {
    try {
      return await request();
    } on TimeoutException catch (error) {
      _connected = false;
      throw BackendNetworkException('Backend request timed out.', error);
    } on http.ClientException catch (error) {
      _connected = false;
      throw BackendNetworkException('Backend network request failed.', error);
    }
  }

  Never _throwHttpError(int statusCode, String body, String operation) {
    _connected = false;
    final detail = _responseDetail(body);
    if (statusCode == 401) {
      throw BackendAuthException(
        'Authentication failed. Check API Key in Settings.',
      );
    }
    if (statusCode == 409) {
      throw SessionConflictException(
        detail.isEmpty
            ? 'Session conflict: another phone session is currently active.'
            : detail,
      );
    }
    if (statusCode == 413) {
      throw PayloadTooLargeException(
        detail.isEmpty ? 'Request exceeds the backend upload limit.' : detail,
      );
    }
    if (statusCode == 503) {
      throw BackendUnavailableException(
        detail.isEmpty ? 'Backend is not ready (HTTP 503).' : detail,
      );
    }
    throw BackendHttpException(
      statusCode,
      '$operation failed (HTTP $statusCode): ${detail.isEmpty ? body : detail}',
    );
  }

  String _responseDetail(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map && decoded['detail'] != null) {
        return decoded['detail'].toString();
      }
    } on FormatException {
      // Keep plain-text error bodies intact.
    }
    return body;
  }

  /// Invalidate responses from requests started before pause/dispose.
  void invalidatePendingOperations() {
    _requestEpoch++;
    _connected = false;
  }

  @override
  Stream<Map<String, dynamic>> get resultsStream => _results.stream;

  @override
  Future<void> connect() async {
    final epoch = _requestEpoch;
    _connected = false;
    final readyUri = Uri.parse('$baseUrl/ready');
    final response = await _networkRequest(
      () => _client
          .get(readyUri, headers: _authAndSessionHeaders)
          .timeout(const Duration(seconds: 8)),
    );
    if (response.statusCode != 200) {
      _throwHttpError(response.statusCode, response.body, 'Readiness check');
    }
    if (epoch == _requestEpoch) _connected = true;
  }

  /// Acquire the single active phone session on the backend.
  Future<Map<String, dynamic>> acquireSession({bool force = false}) async {
    final uri = Uri.parse('$baseUrl/session/acquire');
    final sessionId = _config.sessionId;
    final response = await _networkRequest(
      () => _client
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              ..._headersForSession(sessionId),
            },
            body: jsonEncode({
              'session_id': sessionId,
              'force': force,
              'device_info': 'Flutter Phone App',
            }),
          )
          .timeout(const Duration(seconds: 10)),
    );
    if (response.statusCode != 200) {
      _throwHttpError(response.statusCode, response.body, 'Session acquire');
    }

    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// Release a specific session; the ID is snapshotted for lifecycle safety.
  Future<void> releaseSession({String? sessionId}) async {
    final releaseSessionId = sessionId ?? _config.sessionId;
    final uri = Uri.parse('$baseUrl/session/release');
    final response = await _networkRequest(
      () => _client
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              ..._headersForSession(releaseSessionId),
            },
            body: jsonEncode({'session_id': releaseSessionId}),
          )
          .timeout(const Duration(seconds: 4)),
    );
    if (response.statusCode != 200) {
      _throwHttpError(response.statusCode, response.body, 'Session release');
    }
  }

  /// Test server connection and latency.
  Future<Map<String, dynamic>> testConnection() async {
    final stopwatch = Stopwatch()..start();
    final uri = Uri.parse('$baseUrl/ready');
    final response = await _networkRequest(
      () => _client
          .get(uri, headers: _authAndSessionHeaders)
          .timeout(const Duration(seconds: 8)),
    );
    stopwatch.stop();

    if (response.statusCode != 200) {
      _throwHttpError(response.statusCode, response.body, 'Connection test');
    }

    final data = jsonDecode(response.body) as Map<String, dynamic>;
    data['latency_ms'] = stopwatch.elapsedMilliseconds;
    return data;
  }

  @override
  Future<void> sendFrame(List<int> frameData) async {
    final epoch = _requestEpoch;
    final uri = Uri.parse('$baseUrl/pipeline/frame');
    final request = http.MultipartRequest('POST', uri)
      ..headers.addAll(_authAndSessionHeaders)
      ..files.add(
        http.MultipartFile.fromBytes('file', frameData, filename: 'frame.jpg'),
      );
    final streamed = await _networkRequest(
      () => _client.send(request).timeout(const Duration(seconds: 30)),
    );
    final body = await _networkRequest(streamed.stream.bytesToString);
    if (streamed.statusCode != 200) {
      _throwHttpError(streamed.statusCode, body, 'Frame upload');
    }

    final decoded = jsonDecode(body);
    if (epoch == _requestEpoch && decoded is Map<String, dynamic>) {
      _results.add(decoded);
    }
  }

  void dispose() {
    invalidatePendingOperations();
    _results.close();
    _client.close();
  }
}

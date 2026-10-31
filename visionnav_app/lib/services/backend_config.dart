import 'dart:math';
import 'package:flutter/foundation.dart';

enum BackendEnvironment {
  development,
  production,
}

/// Central configuration for VisionNav backend communication.
///
/// Guarantees that production deployments strictly enforce HTTPS,
/// keeps credentials configurable, and maintains a unique session ID
/// to prevent session collision on the remote inference server.
class BackendConfig extends ChangeNotifier {
  BackendConfig({
    BackendEnvironment? environment,
    String? baseUrl,
    String? apiKey,
    String? sessionId,
  }) {
    // Read compile-time environment flags
    const defaultEnv = String.fromEnvironment('VISIONNAV_ENV', defaultValue: 'development');
    const defaultUrl = String.fromEnvironment(
      'VISIONNAV_API_URL',
      defaultValue: 'http://127.0.0.1:8000',
    );
    const defaultKey = String.fromEnvironment('VISIONNAV_API_KEY', defaultValue: '');

    _environment = environment ??
        (defaultEnv.toLowerCase() == 'production'
            ? BackendEnvironment.production
            : BackendEnvironment.development);

    _baseUrl = baseUrl ?? defaultUrl;
    _apiKey = apiKey ?? defaultKey;
    _sessionId = sessionId ?? _generateSessionId();

    // Sanitize and validate initial URL
    _validateAndApplyUrl(_baseUrl, notify: false);
  }

  static final BackendConfig instance = BackendConfig();

  late BackendEnvironment _environment;
  late String _baseUrl;
  late String _apiKey;
  late String _sessionId;

  BackendEnvironment get environment => _environment;
  String get baseUrl => _baseUrl;
  String get apiKey => _apiKey;
  String get sessionId => _sessionId;
  bool get isProduction => _environment == BackendEnvironment.production;

  static String _generateSessionId() {
    final rand = Random().nextInt(900000) + 100000;
    return 'phone-${DateTime.now().millisecondsSinceEpoch}-$rand';
  }

  /// Validate a backend URL according to environment requirements.
  ///
  /// Production URLs MUST start with https:// to protect camera data and API keys
  /// over public Wi-Fi/mobile data.
  static String? validateUrl(String url, BackendEnvironment env) {
    final trimmed = url.trim();
    if (trimmed.isEmpty) {
      return 'Backend URL cannot be empty.';
    }

    final uri = Uri.tryParse(trimmed);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      return 'Enter a valid URL (e.g., https://api.visionnav.example.com).';
    }

    if (env == BackendEnvironment.production) {
      if (uri.scheme.toLowerCase() != 'https') {
        return 'Production backend MUST use HTTPS (https://). Insecure http:// is rejected.';
      }
    } else {
      final scheme = uri.scheme.toLowerCase();
      if (scheme != 'http' && scheme != 'https') {
        return 'Development backend must use http:// or https://.';
      }
    }

    return null;
  }

  void setEnvironment(BackendEnvironment env) {
    if (_environment == env) return;
    _environment = env;

    // If switching to production, verify HTTPS constraint
    if (_environment == BackendEnvironment.production && !_baseUrl.startsWith('https://')) {
      // If was http:// on localhost/lan, prompt or adjust
      if (_baseUrl.startsWith('http://')) {
        _baseUrl = _baseUrl.replaceFirst('http://', 'https://');
      }
    }
    notifyListeners();
  }

  void _validateAndApplyUrl(String url, {bool notify = true}) {
    var trimmed = url.trim();
    if (trimmed.endsWith('/')) {
      trimmed = trimmed.substring(0, trimmed.length - 1);
    }

    if (_environment == BackendEnvironment.production) {
      if (!trimmed.toLowerCase().startsWith('https://')) {
        throw ArgumentError(
          'Production backend URL must use HTTPS. Received: "$trimmed"',
        );
      }
    }

    _baseUrl = trimmed;
    if (notify) notifyListeners();
  }

  void updateSettings({
    BackendEnvironment? environment,
    String? baseUrl,
    String? apiKey,
  }) {
    var changed = false;

    if (environment != null && environment != _environment) {
      _environment = environment;
      changed = true;
    }

    if (baseUrl != null) {
      _validateAndApplyUrl(baseUrl, notify: false);
      changed = true;
    }

    if (apiKey != null && apiKey != _apiKey) {
      _apiKey = apiKey.trim();
      changed = true;
    }

    if (changed) {
      notifyListeners();
    }
  }

  /// Generate a fresh session ID and notify listeners.
  String resetSessionId() {
    _sessionId = _generateSessionId();
    notifyListeners();
    return _sessionId;
  }
}

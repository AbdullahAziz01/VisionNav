import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:visionnav_app/services/backend_config.dart';
import 'package:visionnav_app/services/navigation/navigation_config.dart';

/// Persists connection settings as one encrypted Android record.
class SavedSettings {
  const SavedSettings({
    required this.environment,
    required this.backendUrl,
    required this.backendKey,
    required this.routingKey,
  });

  static const channel = MethodChannel('visionnav/settings');
  static bool get canPersist =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  final BackendEnvironment environment;
  final String backendUrl;
  final String backendKey;
  final String routingKey;

  static Future<SavedSettings?> read() async {
    if (!canPersist) return null;
    final json = await channel.invokeMethod<String>('read');
    if (json == null) return null;
    final data = jsonDecode(json) as Map<String, dynamic>;
    final settings = SavedSettings(
      environment: BackendEnvironment.values.byName(
        data['environment'] as String,
      ),
      backendUrl: data['backendUrl'] as String,
      backendKey: data['backendKey'] as String,
      routingKey: data['routingKey'] as String,
    );
    if (BackendConfig.validateUrl(settings.backendUrl, settings.environment) !=
        null) {
      throw const FormatException('Saved backend URL is invalid.');
    }
    return settings;
  }

  Future<void> write() async {
    if (!canPersist) return;
    await channel.invokeMethod<void>(
      'write',
      jsonEncode({
        'environment': environment.name,
        'backendUrl': backendUrl,
        'backendKey': backendKey,
        'routingKey': routingKey,
      }),
    );
  }

  void apply() {
    routingApiKey = routingKey;
    BackendConfig.instance.updateSettings(
      environment: environment,
      baseUrl: backendUrl,
      apiKey: backendKey,
    );
  }
}

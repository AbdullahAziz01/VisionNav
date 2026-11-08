import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:visionnav_app/services/backend_config.dart';
import 'package:visionnav_app/services/navigation/navigation_config.dart';
import 'package:visionnav_app/services/saved_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  setUp(() => debugDefaultTargetPlatformOverride = TargetPlatform.android);
  tearDown(() {
    messenger.setMockMethodCallHandler(SavedSettings.channel, null);
    debugDefaultTargetPlatformOverride = null;
  });

  test('restores the saved URL, environment and both keys together', () async {
    String? record;
    messenger.setMockMethodCallHandler(SavedSettings.channel, (call) async {
      if (call.method == 'read') return record;
      expect(call.method, 'write');
      record = call.arguments as String;
      return null;
    });
    expect(await SavedSettings.read(), isNull);
    const settings = SavedSettings(
      environment: BackendEnvironment.production,
      backendUrl: 'https://example.test:8000',
      backendKey: 'test-camera-key',
      routingKey: 'test-routing-key',
    );
    await settings.write();
    final loaded = (await SavedSettings.read())!;
    final config = BackendConfig.instance;
    final original = SavedSettings(
      environment: config.environment,
      backendUrl: config.baseUrl,
      backendKey: config.apiKey,
      routingKey: routingApiKey,
    );
    try {
      loaded.apply();
      expect(config.environment, BackendEnvironment.production);
      expect(config.baseUrl, 'https://example.test:8000');
      expect(config.apiKey, 'test-camera-key');
      expect(routingApiKey, 'test-routing-key');
    } finally {
      original.apply();
    }
  });

  test('rejects a stored HTTP URL in production mode', () async {
    messenger.setMockMethodCallHandler(
      SavedSettings.channel,
      (_) async => jsonEncode({
        'environment': 'production',
        'backendUrl': 'http://example.test',
        'backendKey': '',
        'routingKey': '',
      }),
    );
    await expectLater(SavedSettings.read(), throwsFormatException);
  });
}

import 'package:visionnav_app/services/voice_commands.dart';
import 'package:flutter/material.dart';
import 'package:visionnav_app/services/backend_config.dart';
import 'package:visionnav_app/services/navigation/navigation_config.dart';
import 'package:visionnav_app/services/visionnav_api.dart';
import 'package:visionnav_app/services/saved_settings.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _formKey = GlobalKey<FormState>();
  late final BackendConfig _config;
  late BackendEnvironment _environment;
  bool _saving = false;
  late final TextEditingController _urlController;
  late final TextEditingController _apiKeyController;
  late final TextEditingController _routingKeyController;

  final _voice = VoiceCommands.shared;
  String? _voiceField;
  String? _pendingValue;
  bool _pendingTakeover = false;

  Future<bool> _handleVoice(String words) async {
    if (!mounted || ModalRoute.of(context)?.isCurrent != true) return false;
    final c = normalizeCommand(words);
    if (c == 'cancel' && (_voiceField != null || _pendingTakeover)) {
      _voiceField = null;
      _pendingValue = null;
      _pendingTakeover = false;
      await _voice.say('Change cancelled.');
      return true;
    }
    if (c == 'confirm' && _pendingTakeover) {
      _pendingTakeover = false;
      await _forceTakeoverSession();
      return true;
    }
    if (c == 'confirm' && _voiceField != null && _pendingValue != null) {
      final controller = _voiceField == 'backend url'
          ? _urlController
          : _voiceField == 'api key'
          ? _apiKeyController
          : _routingKeyController;
      controller.text = _pendingValue!;
      _voiceField = null;
      _pendingValue = null;
      await _voice.say('Field updated. Say save settings to apply it.');
      return true;
    }
    if (_voiceField != null &&
        _pendingValue == null &&
        !isGlobalVoiceCommand(c)) {
      _pendingValue = words.trim();
      await _voice.say(
        _voiceField == 'backend url'
            ? 'URL received: $_pendingValue. Say confirm or cancel.'
            : 'Key received. Say confirm or cancel. The key will not be read aloud.',
      );
      return true;
    }
    if (c == 'edit backend url' ||
        c == 'edit api key' ||
        c == 'edit routing key') {
      _voiceField = c.substring(5);
      _pendingValue = null;
      await _voice.say('Say the exact $_voiceField, or cancel.');
    } else if (c == 'save settings' || c == 'save') {
      await _saveSettings();
    } else if (c == 'test connection' || c == 'test server connection') {
      if (!_testingConnection) await _testConnection();
    } else if (c == 'new session' || c == 'new session id') {
      _generateNewSession();
      await _voice.say('New session ID generated.');
    } else if (c == 'force takeover') {
      _pendingTakeover = true;
      await _voice.say(
        'This will take over the backend session from another phone. Say confirm or cancel.',
      );
    } else if (c == 'show api key' || c == 'hide api key') {
      setState(() => _obscureApiKey = c == 'hide api key');
      await _voice.say(
        _obscureApiKey ? 'Key hidden.' : 'Key visible on screen.',
      );
    } else if (c == 'development mode' || c == 'production mode') {
      final env = c == 'development mode'
          ? BackendEnvironment.development
          : BackendEnvironment.production;
      setState(() {
        _environment = env;
        if (env == BackendEnvironment.production &&
            _urlController.text.startsWith('http://')) {
          _urlController.text = _urlController.text.replaceFirst(
            'http://',
            'https://',
          );
        }
      });
      await _voice.say('$c selected. Save settings to apply the address.');
    } else if (c == 'screen commands') {
      await _voice.say(
        'Say save settings, test connection, edit backend URL, edit API key, edit routing key, show API key, hide API key, development mode, production mode, new session, or force takeover.',
      );
    } else {
      return false;
    }
    return true;
  }

  bool _obscureApiKey = true;
  bool _testingConnection = false;
  String? _testResult;
  bool _testSuccess = false;

  @override
  void initState() {
    super.initState();
    _voice.register(this, _handleVoice);
    _config = BackendConfig.instance;
    _environment = _config.environment;
    _urlController = TextEditingController(text: _config.baseUrl);
    _apiKeyController = TextEditingController(text: _config.apiKey);
    _routingKeyController = TextEditingController(text: routingApiKey);
  }

  @override
  void dispose() {
    _voice.unregister(this);
    _urlController.dispose();
    _apiKeyController.dispose();
    _routingKeyController.dispose();
    super.dispose();
  }

  Future<bool> _saveSettings() async {
    if (_saving || !mounted) return false;
    if (!_formKey.currentState!.validate()) {
      await _voice.say(
        'Check the backend URL. It is invalid for the selected mode.',
      );
      return false;
    }

    final settings = SavedSettings(
      environment: _environment,
      backendUrl: _urlController.text.trim(),
      backendKey: _apiKeyController.text.trim(),
      routingKey: _routingKeyController.text.trim(),
    );
    setState(() => _saving = true);
    try {
      await settings.write();
      settings.apply();
      if (mounted) {
        final message = SavedSettings.canPersist
            ? 'Settings saved on this device.'
            : 'Settings applied for this session.';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(message), backgroundColor: Colors.teal),
        );
        await _voice.say(message);
      }
      return true;
    } catch (_) {
      if (mounted) {
        const message =
            'Could not save settings on this device. Please try again.';
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(message),
            backgroundColor: Colors.redAccent,
          ),
        );
        await _voice.say(message);
      }
      return false;
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _testConnection() async {
    if (_testingConnection || !await _saveSettings() || !mounted) return;
    setState(() {
      _testingConnection = true;
      _testResult = null;
    });

    final api = HttpVisionNavApi(config: _config);
    try {
      final info = await api.testConnection();
      if (!mounted) return;
      await _voice.say('Backend connected successfully.');
      if (!mounted) return;
      setState(() {
        _testingConnection = false;
        _testSuccess = true;
        _testResult =
            'Connected in ${info['latency_ms']} ms\n'
            'Model: ${info['yolo_model'] ?? 'Ready'}\n'
            'Depth Backend: ${info['mono_depth_backend'] ?? 'Ready'}\n'
            'Auth: ${info['auth_enabled'] == true ? 'Protected' : 'Open (Dev)'}';
      });
    } catch (e) {
      if (!mounted) return;
      await _voice.say(
        'Connection failed. Check the server address, key, and Wi-Fi.',
      );
      if (!mounted) return;
      setState(() {
        _testingConnection = false;
        _testSuccess = false;
        _testResult = 'Connection Failed: $e';
      });
    } finally {
      api.dispose();
    }
  }

  Future<void> _forceTakeoverSession() async {
    final api = HttpVisionNavApi(config: _config);
    try {
      final res = await api.acquireSession(force: true);
      if (!mounted) return;
      await _voice.say('Backend session acquired.');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Session acquired: ${res['message'] ?? 'OK'}'),
          backgroundColor: Colors.teal,
        ),
      );
      setState(() {});
    } catch (e) {
      if (!mounted) return;
      await _voice.say('Session takeover failed.');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Takeover failed: $e'),
          backgroundColor: Colors.redAccent,
        ),
      );
    } finally {
      api.dispose();
    }
  }

  void _generateNewSession() {
    final newId = _config.resetSessionId();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Generated fresh session ID: $newId'),
        backgroundColor: Colors.teal,
      ),
    );
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final isProd = _environment == BackendEnvironment.production;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings & Backend'),
        actions: [
          IconButton(
            icon: const Icon(Icons.check),
            tooltip: 'Save',
            onPressed: _saving ? null : _saveSettings,
          ),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16.0),
          children: [
            // Environment Selector
            const Text(
              'Deployment Environment',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            const SizedBox(height: 8),
            SegmentedButton<BackendEnvironment>(
              segments: const [
                ButtonSegment(
                  value: BackendEnvironment.development,
                  label: Text('Development'),
                  icon: Icon(Icons.developer_mode),
                ),
                ButtonSegment(
                  value: BackendEnvironment.production,
                  label: Text('Production (HTTPS)'),
                  icon: Icon(Icons.security),
                ),
              ],
              selected: {_environment},
              onSelectionChanged: (set) {
                final chosen = set.first;
                setState(() {
                  _environment = chosen;
                  if (chosen == BackendEnvironment.production &&
                      _urlController.text.startsWith('http://')) {
                    _urlController.text = _urlController.text.replaceFirst(
                      'http://',
                      'https://',
                    );
                  }
                });
              },
            ),
            const SizedBox(height: 12),
            if (isProd)
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.teal.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.teal.shade400),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.lock, color: Colors.tealAccent, size: 20),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Production Mode: Insecure HTTP is blocked. Server communication must use HTTPS.',
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.tealAccent,
                        ),
                      ),
                    ),
                  ],
                ),
              )
            else
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.amber.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.amber.shade400),
                ),
                child: const Row(
                  children: [
                    Icon(
                      Icons.info_outline,
                      color: Colors.amberAccent,
                      size: 20,
                    ),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Development Mode: HTTP and LAN addresses allowed for local testing.',
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.amberAccent,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 20),

            TextFormField(
              controller: _routingKeyController,
              obscureText: true,
              autocorrect: false,
              enableSuggestions: false,
              decoration: const InputDecoration(
                labelText: 'OpenRouteService key',
                helperText:
                    'Required for walking directions. Tap Save to keep your key.',
                helperMaxLines: 2,
              ),
            ),
            const SizedBox(height: 20),

            // Backend URL
            const Text(
              'Remote Backend URL',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            const SizedBox(height: 4),
            TextFormField(
              controller: _urlController,
              keyboardType: TextInputType.url,
              decoration: InputDecoration(
                hintText: isProd
                    ? 'https://api.visionnav.yourdomain.com'
                    : 'http://192.168.1.100:8000',
                labelText: 'Backend URL',
                prefixIcon: Icon(isProd ? Icons.https : Icons.link),
                border: const OutlineInputBorder(),
                helperText: isProd
                    ? 'Production requires a valid HTTPS URL.'
                    : 'Use local IP or adb reverse 127.0.0.1.',
              ),
              validator: (val) =>
                  BackendConfig.validateUrl(val ?? '', _environment),
            ),
            const SizedBox(height: 20),

            // API Key
            const Text(
              'Backend API Key / Access Token',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            const SizedBox(height: 4),
            TextFormField(
              controller: _apiKeyController,
              obscureText: _obscureApiKey,
              decoration: InputDecoration(
                labelText: 'Backend API key',
                hintText: 'Optional for dev; required for protected servers',
                prefixIcon: const Icon(Icons.key),
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                  tooltip: _obscureApiKey ? 'Show API key' : 'Hide API key',
                  icon: Icon(
                    _obscureApiKey ? Icons.visibility : Icons.visibility_off,
                  ),
                  onPressed: () {
                    setState(() => _obscureApiKey = !_obscureApiKey);
                  },
                ),
                helperText:
                    'Kept in client configuration, outside source code.',
              ),
            ),
            const SizedBox(height: 24),

            // Session Isolation
            const Text(
              'Session Isolation (Anti-Mixing)',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            const SizedBox(height: 4),
            Text(
              'Active Session ID: ${_config.sessionId}',
              style: const TextStyle(fontSize: 13, color: Colors.white70),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.refresh, size: 18),
                    label: const Text('New Session ID'),
                    onPressed: _generateNewSession,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.bolt, size: 18),
                    label: const Text('Force Takeover'),
                    onPressed: _forceTakeoverSession,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),

            // Test Connection Button
            ElevatedButton.icon(
              icon: _testingConnection
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.network_check),
              label: Text(
                _testingConnection ? 'Testing...' : 'Test Server Connection',
              ),
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14),
                backgroundColor: Colors.teal.shade700,
                foregroundColor: Colors.white,
              ),
              onPressed: _testingConnection ? null : _testConnection,
            ),
            const SizedBox(height: 12),

            if (_testResult != null)
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _testSuccess
                      ? Colors.teal.withValues(alpha: 0.2)
                      : Colors.redAccent.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: _testSuccess ? Colors.teal : Colors.redAccent,
                  ),
                ),
                child: Text(
                  _testResult!,
                  style: TextStyle(
                    color: _testSuccess
                        ? Colors.tealAccent
                        : Colors.redAccent.shade100,
                    fontFamily: 'monospace',
                    fontSize: 13,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

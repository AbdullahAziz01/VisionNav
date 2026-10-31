import 'package:flutter/material.dart';
import 'package:visionnav_app/services/backend_config.dart';
import 'package:visionnav_app/services/visionnav_api.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({Key? key}) : super(key: key);

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _formKey = GlobalKey<FormState>();
  late final BackendConfig _config;
  late final TextEditingController _urlController;
  late final TextEditingController _apiKeyController;

  bool _obscureApiKey = true;
  bool _testingConnection = false;
  String? _testResult;
  bool _testSuccess = false;

  @override
  void initState() {
    super.initState();
    _config = BackendConfig.instance;
    _urlController = TextEditingController(text: _config.baseUrl);
    _apiKeyController = TextEditingController(text: _config.apiKey);
  }

  @override
  void dispose() {
    _urlController.dispose();
    _apiKeyController.dispose();
    super.dispose();
  }

  void _saveSettings() {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    try {
      _config.updateSettings(
        baseUrl: _urlController.text.trim(),
        apiKey: _apiKeyController.text.trim(),
      );
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Settings saved successfully.'),
          backgroundColor: Colors.teal,
        ),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Save error: $e'),
          backgroundColor: Colors.redAccent,
        ),
      );
    }
  }

  Future<void> _testConnection() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    _saveSettings();
    setState(() {
      _testingConnection = true;
      _testResult = null;
    });

    final api = HttpVisionNavApi(config: _config);
    try {
      final info = await api.testConnection();
      setState(() {
        _testingConnection = false;
        _testSuccess = true;
        _testResult = 'Connected in ${info['latency_ms']} ms\n'
            'Model: ${info['yolo_model'] ?? 'Ready'}\n'
            'Depth Backend: ${info['mono_depth_backend'] ?? 'Ready'}\n'
            'Auth: ${info['auth_enabled'] == true ? 'Protected' : 'Open (Dev)'}';
      });
    } catch (e) {
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
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Session acquired: ${res['message'] ?? 'OK'}'),
          backgroundColor: Colors.teal,
        ),
      );
      setState(() {});
    } catch (e) {
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
    final isProd = _config.isProduction;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings & Backend'),
        actions: [
          IconButton(
            icon: const Icon(Icons.check),
            tooltip: 'Save',
            onPressed: _saveSettings,
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
              selected: {_config.environment},
              onSelectionChanged: (set) {
                final chosen = set.first;
                setState(() {
                  _config.setEnvironment(chosen);
                  if (chosen == BackendEnvironment.production &&
                      _urlController.text.startsWith('http://')) {
                    _urlController.text =
                        _urlController.text.replaceFirst('http://', 'https://');
                  }
                });
              },
            ),
            const SizedBox(height: 12),
            if (isProd)
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.teal.withOpacity(0.15),
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
                        style: TextStyle(fontSize: 13, color: Colors.tealAccent),
                      ),
                    ),
                  ],
                ),
              )
            else
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.amber.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.amber.shade400),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.info_outline, color: Colors.amberAccent, size: 20),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Development Mode: HTTP and LAN addresses allowed for local testing.',
                        style: TextStyle(fontSize: 13, color: Colors.amberAccent),
                      ),
                    ),
                  ],
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
                prefixIcon: Icon(isProd ? Icons.https : Icons.link),
                border: const OutlineInputBorder(),
                helperText: isProd
                    ? 'Production requires a valid HTTPS URL.'
                    : 'Use local IP or adb reverse 127.0.0.1.',
              ),
              validator: (val) => BackendConfig.validateUrl(
                val ?? '',
                _config.environment,
              ),
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
                hintText: 'Optional for dev; required for protected servers',
                prefixIcon: const Icon(Icons.key),
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                  icon: Icon(_obscureApiKey ? Icons.visibility : Icons.visibility_off),
                  onPressed: () {
                    setState(() => _obscureApiKey = !_obscureApiKey);
                  },
                ),
                helperText: 'Kept in client configuration, outside source code.',
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
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.network_check),
              label: Text(_testingConnection ? 'Testing...' : 'Test Server Connection'),
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
                      ? Colors.teal.withOpacity(0.2)
                      : Colors.redAccent.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: _testSuccess ? Colors.teal : Colors.redAccent,
                  ),
                ),
                child: Text(
                  _testResult!,
                  style: TextStyle(
                    color: _testSuccess ? Colors.tealAccent : Colors.redAccent.shade100,
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

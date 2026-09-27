import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:visionnav_app/services/service_interfaces.dart';

/// PC FastAPI URL.
///
/// USB (recommended): run `adb reverse tcp:8000 tcp:8000` then use 127.0.0.1
/// so the phone does not depend on a changing Wi-Fi IP.
/// Wi-Fi: set this to `http://PC_LAN_IP:8000` and rebuild.
const String kVisionNavApiBaseUrl = String.fromEnvironment(
  'VISIONNAV_API_URL',
  defaultValue: 'http://127.0.0.1:8000',
);

class HttpVisionNavApi implements VisionNavApi {
  HttpVisionNavApi({this.baseUrl = kVisionNavApiBaseUrl});

  final String baseUrl;
  final StreamController<Map<String, dynamic>> _results =
      StreamController<Map<String, dynamic>>.broadcast();

  bool _connected = false;

  bool get isConnected => _connected;

  @override
  Stream<Map<String, dynamic>> get resultsStream => _results.stream;

  @override
  Future<void> connect() async {
    final uri = Uri.parse('$baseUrl/pipeline/status');
    final response = await http.get(uri).timeout(const Duration(seconds: 8));
    if (response.statusCode != 200) {
      throw Exception('API status ${response.statusCode}: ${response.body}');
    }
    _connected = true;
  }

  @override
  Future<void> sendFrame(List<int> frameData) async {
    final uri = Uri.parse('$baseUrl/pipeline/frame');
    final request = http.MultipartRequest('POST', uri)
      ..files.add(
        http.MultipartFile.fromBytes(
          'file',
          frameData,
          filename: 'frame.jpg',
        ),
      );

    final streamed = await request.send().timeout(const Duration(seconds: 30));
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode != 200) {
      throw Exception('Frame upload failed (${streamed.statusCode}): $body');
    }

    final decoded = jsonDecode(body);
    if (decoded is Map<String, dynamic>) {
      _results.add(decoded);
    }
  }

  void dispose() {
    _connected = false;
    _results.close();
  }
}

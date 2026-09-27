abstract class VisionNavApi {
  Future<void> connect();
  Future<void> sendFrame(List<int> frameData);
  Stream<Map<String, dynamic>> get resultsStream;
}

abstract class LocationService {
  Future<bool> requestPermissions();
  Stream<Map<String, double>> get locationStream;
}

abstract class NavigationService {
  Future<void> setDestination(String destination);
  Future<void> startNavigation();
  Future<void> stopNavigation();
}

abstract class SpeechRecognitionService {
  Future<void> startListening();
  Future<void> stopListening();
  Stream<String> get textStream;
}

abstract class TtsService {
  Future<void> speak(String text);
  Future<void> stop();
}

abstract class VoiceCommandManager {
  void handleCommand(String command);
}

abstract class ModeManager {
  void switchMode(String mode);
  String get currentMode;
}

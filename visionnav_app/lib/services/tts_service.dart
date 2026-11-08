import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:visionnav_app/services/service_interfaces.dart';

/// Android Text-to-Speech via the platform TTS engine (flutter_tts).
///
/// `speak()` hands the text to the OS engine and returns immediately; speech
/// runs on the platform side, so it never blocks the camera preview or the
/// frame-upload loop. [isSpeaking] lets callers avoid piling up phrases.
class FlutterTtsService implements TtsService {
  FlutterTtsService({this.speechRate = 0.5, this.language = 'en-US'});

  /// One engine for the whole app. flutter_tts uses a single platform channel,
  /// so separate instances would overwrite each other's start/complete handlers.
  static final FlutterTtsService shared = FlutterTtsService();

  final double speechRate; // 0.0–1.0, 0.5 is the Android "normal" pace
  final String language;

  final FlutterTts _tts = FlutterTts();
  bool _ready = false;
  bool _speaking = false;
  bool _cameraSpeech = false;
  int _navigationRequests = 0;
  int _speechGeneration = 0;

  bool get canSpeakCamera =>
      !_speaking && !_cameraSpeech && _navigationRequests == 0;

  Future<void> speakCamera(String text) async {
    if (!canSpeakCamera) return;
    _cameraSpeech = true;
    try {
      await speakAndWait(text);
    } finally {
      _cameraSpeech = false;
    }
  }

  Future<void> stopCameraSpeech() async {
    if (!_cameraSpeech) return;
    _cameraSpeech = false;
    await stop();
  }

  Future<void> speakNavigation(String text) async {
    _navigationRequests++;
    try {
      await stopCameraSpeech();
      await speak(text);
    } finally {
      _navigationRequests--;
    }
  }

  Timer? _stuckGuard;
  Duration _speechTimeout = const Duration(seconds: 10);
  Completer<void>? _idle;

  Future<void> Function()? beforeSpeak;

  bool get isSpeaking => _speaking;
  bool get isReady => _ready;

  Future<void> initialize() async {
    if (_ready) return;
    try {
      await _tts.setLanguage(language);
      await _tts.setSpeechRate(speechRate);
      await _tts.setVolume(1.0);
      await _tts.setPitch(1.0);
      try {
        // QUEUE_ADD: consecutive phrases (e.g. "In 40 metres, turn left" then
        // "Turn left") play one after another instead of cutting each other off.
        await _tts.setQueueMode(1);
      } catch (_) {
        // Not supported on this platform; flush mode is acceptable.
      }
      _tts.setStartHandler(() => _setSpeaking(true));
      _tts.setCompletionHandler(() => _setSpeaking(false));
      _tts.setCancelHandler(() => _setSpeaking(false));
      _tts.setErrorHandler((msg) {
        debugPrint('TTS error: $msg');
        _setSpeaking(false);
      });
      _ready = true;
    } catch (e) {
      debugPrint('TTS init failed: $e');
    }
  }

  @override
  Future<void> speak(String text) async {
    final generation = _speechGeneration;
    if (!_ready) await initialize();
    if (!_ready || text.isEmpty || generation != _speechGeneration) return;
    _speechTimeout = Duration(
      seconds: (text.split(RegExp(r'\s+')).length * 0.8 + 8).ceil().clamp(
        10,
        180,
      ),
    );
    _setSpeaking(true);
    try {
      await beforeSpeak?.call();
      if (generation == _speechGeneration) await _tts.speak(text);
    } catch (e) {
      debugPrint('TTS speak failed: $e');
      _setSpeaking(false);
    }
  }

  /// Speaks [text] and resolves when the engine finishes (or times out).
  /// Used by the Nav prompt so the microphone does not start mid-sentence.
  Future<void> speakAndWait(String text) async {
    final generation = _speechGeneration;
    await speak(text);
    if (!_speaking || generation != _speechGeneration) return;
    await (_idle?.future ?? Future<void>.value());
  }

  @override
  Future<void> stop() async {
    _speechGeneration++;
    _stuckGuard?.cancel();
    if (!_ready) {
      _setSpeaking(false);
      return;
    }
    try {
      await _tts.stop();
    } catch (_) {}
    _setSpeaking(false);
  }

  void _setSpeaking(bool value) {
    _speaking = value;
    _stuckGuard?.cancel();
    if (value) {
      if (_idle == null || _idle!.isCompleted) {
        _idle = Completer<void>();
      }
      // Allow long spoken menus to finish before recognition resumes.
      _stuckGuard = Timer(_speechTimeout, () => _setSpeaking(false));
    } else if (_idle != null && !_idle!.isCompleted) {
      _idle!.complete();
    }
  }

  Future<void> dispose() async {
    await stop();
  }
}

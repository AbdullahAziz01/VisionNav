import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:visionnav_app/services/service_interfaces.dart';

class SpeechUnavailableException implements Exception {
  SpeechUnavailableException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Android speech recognition via the `speech_to_text` plugin.
///
/// [textStream] emits live (partial) transcripts for the UI.
/// [finalResults] emits one phrase when the recognizer finishes an utterance.
/// [listenEnded] fires when a listen session stops with no usable phrase.
class SpeechToTextService implements SpeechRecognitionService {
  SpeechToTextService({SpeechToText? engine}) : _engine = engine ?? SpeechToText();

  final SpeechToText _engine;
  final StreamController<String> _text = StreamController<String>.broadcast();
  final StreamController<String> _finals = StreamController<String>.broadcast();
  final StreamController<void> _ended = StreamController<void>.broadcast();

  bool _initialized = false;
  bool _listening = false;
  String _lastWords = '';
  bool _emittedFinal = false;

  bool get isListening => _listening;

  @override
  Stream<String> get textStream => _text.stream;

  Stream<String> get finalResults => _finals.stream;

  Stream<void> get listenEnded => _ended.stream;

  Future<void> initialize() async {
    if (_initialized) return;
    final mic = await Permission.microphone.request();
    if (!mic.isGranted) {
      throw SpeechUnavailableException(
        'Microphone permission denied. Enable it in Settings to speak a destination.',
      );
    }
    final ok = await _engine.initialize(
      onError: (error) {
        debugPrint('Speech error: ${error.errorMsg}');
        _finishListen();
      },
      onStatus: (status) {
        if (status == SpeechToText.doneStatus ||
            status == SpeechToText.notListeningStatus) {
          _finishListen();
        }
      },
    );
    if (!ok) {
      throw SpeechUnavailableException(
        'Speech recognition is not available on this device.',
      );
    }
    _initialized = true;
  }

  @override
  Future<void> startListening() async {
    await initialize();
    if (_listening) return;
    _lastWords = '';
    _emittedFinal = false;
    _listening = true;
    await _engine.listen(
      onResult: (result) {
        final words = result.recognizedWords.trim();
        if (words.isEmpty) return;
        _lastWords = words;
        _text.add(words);
        if (result.finalResult) {
          _emitFinal(words);
        }
      },
      listenOptions: SpeechListenOptions(
        listenFor: const Duration(seconds: 10),
        pauseFor: const Duration(seconds: 3),
        partialResults: true,
        cancelOnError: true,
        listenMode: ListenMode.confirmation,
        localeId: 'en_US',
      ),
    );
  }

  @override
  Future<void> stopListening() async {
    if (!_initialized) return;
    try {
      await _engine.stop();
    } catch (_) {}
    _finishListen();
  }

  void _emitFinal(String words) {
    if (_emittedFinal || words.isEmpty) return;
    _emittedFinal = true;
    _finals.add(words);
  }

  void _finishListen() {
    if (!_listening && _emittedFinal) return;
    final wasListening = _listening;
    _listening = false;
    if (!_emittedFinal && _lastWords.isNotEmpty) {
      _emitFinal(_lastWords);
    } else if (wasListening && !_emittedFinal) {
      _ended.add(null);
    }
  }

  Future<void> dispose() async {
    await stopListening();
    await _text.close();
    await _finals.close();
    await _ended.close();
  }
}

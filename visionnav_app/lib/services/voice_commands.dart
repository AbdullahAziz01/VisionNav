import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:visionnav_app/services/speech_recognition_service.dart';
import 'package:visionnav_app/services/tts_service.dart';

String normalizeCommand(String text) => text
    .toLowerCase()
    .replaceAll(RegExp(r'[^a-z0-9 ]'), ' ')
    .replaceAll(RegExp(r'\s+'), ' ')
    .trim();

bool isGlobalVoiceCommand(String command) => const {
  'open home',
  'home',
  'go home',
  'open vision',
  'open camera',
  'camera',
  'scan bus',
  'open visionnav',
  'open vision nav',
  'add location',
  'open gps',
  'open navigation',
  'navigation',
  'open settings',
  'settings',
  'open help',
  'help',
  'plan a bus trip',
  'plan bus trip',
  'go back',
  'back',
  'cancel',
  'end bus trip',
  'screen commands',
  'read help',
  'voice help',
  'what can i say',
  'stop listening',
  'pause voice commands',
}.contains(command);

int? spokenNumber(String value) {
  const numbers = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5};
  return numbers[value] ?? int.tryParse(value);
}

String routeVoiceKey(String value) => normalizeCommand(value)
    .replaceAll(' ', '')
    .replaceAllMapped(
      RegExp(r'\d+'),
      (match) => int.parse(match[0]!).toString(),
    );

typedef VoiceHandler = Future<bool> Function(String command);

/// One foreground command listener. Destination entry temporarily owns the same
/// recognizer. Speech playback cancels recognition before audio starts.
class VoiceCommands extends ChangeNotifier with WidgetsBindingObserver {
  static final shared = VoiceCommands();
  VoiceCommands({SpeechToTextService? speech, FlutterTtsService? tts})
    : speech = speech ?? SpeechToTextService.shared,
      tts = tts ?? FlutterTtsService.shared;
  final SpeechToTextService speech;
  final FlutterTtsService tts;
  final Map<Object, VoiceHandler> _handlers = {};
  final Set<Object> _holds = {};
  StreamSubscription<String>? _results;
  StreamSubscription<String>? _failures;
  Timer? _timer;
  bool enabled = false;
  bool _foreground = true;
  bool _busy = false;
  bool _starting = false;
  Completer<void>? _listenDone;
  bool _discard = false;
  String status = 'Voice commands off';

  void register(Object owner, VoiceHandler handler) =>
      _handlers[owner] = handler;
  void unregister(Object owner) => _handlers.remove(owner);

  Future<void> start() async {
    if (enabled) return;
    enabled = true;
    WidgetsBinding.instance.addObserver(this);
    tts.beforeSpeak = _beforeSpeech;
    _foreground =
        WidgetsBinding.instance.lifecycleState == null ||
        WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed;
    _results = speech.finalResults.listen(_onResult);
    _failures = speech.failures.listen((_) async {
      await stop();
      status =
          'Speech interrupted. Check microphone and network; tap Resume voice.';
      notifyListeners();
      await say(
        'Speech recognition is unavailable. Check microphone permission and your connection, then resume voice.',
      );
    });
    status = 'Starting voice commands';
    notifyListeners();
    try {
      await speech.initialize();
      if (!enabled) return;
      _timer = Timer.periodic(
        const Duration(milliseconds: 800),
        (_) => _listen(),
      );
      await say(
        'VisionNav is open. Say add location, open home, plan a bus trip, or voice help.',
      );
    } catch (_) {
      await stop();
      status =
          'Speech unavailable. Check microphone permission and tap Resume voice.';
      notifyListeners();
    }
  }

  Future<void> stop() async {
    enabled = false;
    _timer?.cancel();
    _timer = null;
    await _failures?.cancel();
    _failures = null;
    await _results?.cancel();
    _results = null;
    await speech.cancelListening();
    WidgetsBinding.instance.removeObserver(this);
    tts.beforeSpeak = null;
    status = 'Voice commands off';
    notifyListeners();
  }

  Future<void> hold(Object owner) async {
    _holds.add(owner);
    await _listenDone?.future;
    await speech.cancelListening();
  }

  void release(Object owner) => _holds.remove(owner);

  Future<void> _beforeSpeech() async {
    // Destination prompts already stop their own recognition.
    if (_holds.isNotEmpty) return;
    _discard = true;
    await speech.cancelListening();
    _discard = false;
  }

  Future<void> say(String text) => tts.speakAndWait(text);

  Future<void> _listen() async {
    if (!enabled ||
        !_foreground ||
        _busy ||
        _starting ||
        _holds.isNotEmpty ||
        tts.isSpeaking ||
        speech.isListening) {
      return;
    }
    _starting = true;
    _listenDone = Completer<void>();
    try {
      await speech.startListening();
      if (!enabled || !_foreground || _holds.isNotEmpty || tts.isSpeaking) {
        await speech.cancelListening();
        return;
      }
      status = 'Listening for a command';
      notifyListeners();
    } catch (_) {
      await stop();
      status = 'Speech unavailable. Tap Resume voice to retry.';
      notifyListeners();
    } finally {
      _starting = false;
      _listenDone?.complete();
      _listenDone = null;
    }
  }

  Future<void> _onResult(String words) async {
    if (!enabled ||
        !_foreground ||
        _busy ||
        _discard ||
        _holds.isNotEmpty ||
        tts.isSpeaking) {
      return;
    }
    _busy = true;
    await speech.cancelListening();
    if (!enabled || !_foreground) {
      _busy = false;
      return;
    }
    final command = normalizeCommand(words);
    // Do not display transcripts: a settings command may contain a secret.
    status = 'Processing voice command';
    notifyListeners();
    try {
      if (command == 'stop listening' || command == 'pause voice commands') {
        await say('Voice commands paused. Use Resume voice to listen again.');
        await stop();
        return;
      }
      if (await dispatch(words)) return;
      await say(
        'Command not recognized. Say voice help for available commands.',
      );
    } catch (_) {
      await say(
        'That action could not finish. Please try again or use the touch control.',
      );
    } finally {
      _busy = false;
    }
  }

  Future<bool> dispatch(String words) async {
    for (final handler in _handlers.values.toList().reversed) {
      if (await handler(words.trim())) return true;
    }
    return false;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    if (!_foreground) unawaited(speech.cancelListening());
  }
}

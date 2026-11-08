import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:visionnav_app/services/voice_commands.dart';
import 'package:visionnav_app/services/speech_recognition_service.dart';
import 'package:visionnav_app/services/tts_service.dart';

class FakeSpeech extends SpeechToTextService {
  final results = StreamController<String>.broadcast();
  final errors = StreamController<String>.broadcast();
  bool listening = false;
  int starts = 0;
  @override
  Stream<String> get finalResults => results.stream;
  @override
  Stream<String> get failures => errors.stream;
  @override
  bool get isListening => listening;
  @override
  Future<void> initialize() async {}
  @override
  Future<void> startListening() async {
    starts++;
    listening = true;
  }

  @override
  Future<void> cancelListening() async {
    listening = false;
  }
}

class FakeTts extends FlutterTtsService {
  final messages = <String>[];
  bool speaking = false;
  @override
  bool get isSpeaking => speaking;
  @override
  Future<void> speakAndWait(String text) async {
    speaking = true;
    await beforeSpeak?.call();
    messages.add(text);
    speaking = false;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'exact commands do not consume destination names containing keywords',
    () {
      expect(isGlobalVoiceCommand(normalizeCommand('OPEN GPS!')), isTrue);
      expect(
        isGlobalVoiceCommand(normalizeCommand('Home Economics College')),
        isFalse,
      );
      expect(isGlobalVoiceCommand('camera market'), isFalse);
      expect(routeVoiceKey('FR-01'), routeVoiceKey('F R 1'));
      expect(routeVoiceKey('FR-10'), isNot(routeVoiceKey('FR-1')));
      expect(routeVoiceKey('FR-101'), isNot(routeVoiceKey('FR-11')));
    },
  );
  test('active handler wins; removing it restores global routing', () async {
    final voice = VoiceCommands(speech: FakeSpeech(), tts: FakeTts());
    final called = <String>[];
    final global = Object(), screen = Object();
    voice.register(global, (_) async {
      called.add('global');
      return true;
    });
    voice.register(screen, (_) async {
      called.add('screen');
      return true;
    });
    expect(await voice.dispatch('continue'), isTrue);
    expect(called, ['screen']);
    voice.unregister(screen);
    await voice.dispatch('open home');
    expect(called, ['screen', 'global']);
    voice.unregister(global);
    expect(await voice.dispatch('unknown'), isFalse);
  });
  test(
    'foreground listener yields to destination, TTS, and background',
    () async {
      final speech = FakeSpeech(), tts = FakeTts();
      final voice = VoiceCommands(speech: speech, tts: tts);
      final owner = Object();
      final commands = <String>[];
      voice.register(owner, (words) async {
        commands.add(words);
        return true;
      });
      await voice.start();
      voice.didChangeAppLifecycleState(AppLifecycleState.resumed);
      await Future<void>.delayed(const Duration(seconds: 1));
      expect(speech.listening, isTrue);
      await voice.hold(owner);
      speech.results.add('PIMS Hospital');
      await Future<void>.delayed(const Duration(seconds: 1));
      expect(commands, isEmpty);
      expect(speech.listening, isFalse);
      voice.release(owner);
      await Future<void>.delayed(const Duration(seconds: 1));
      expect(speech.listening, isTrue);
      await voice.say('A spoken instruction');
      expect(speech.listening, isFalse);
      tts.speaking = true;
      await Future<void>.delayed(const Duration(seconds: 1));
      expect(speech.listening, isFalse);
      tts.speaking = false;
      await Future<void>.delayed(const Duration(seconds: 1));
      speech.results.add('open home');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(commands, ['open home']);
      voice.didChangeAppLifecycleState(AppLifecycleState.paused);
      await Future<void>.delayed(const Duration(seconds: 2));
      expect(speech.listening, isFalse);
      speech.results.add('open settings');
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(commands, ['open home']);
      final stopping = voice.stop();
      await Future<void>.delayed(const Duration(milliseconds: 20));
      await stopping;
      await speech.results.close();
      await speech.errors.close();
    },
  );
  test('recognizer error stops retry loop and exposes recovery', () async {
    final speech = FakeSpeech(), tts = FakeTts();
    final voice = VoiceCommands(speech: speech, tts: tts);
    await voice.start();
    speech.errors.add('error_network');
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(voice.enabled, isFalse);
    final count = speech.starts;
    await Future<void>.delayed(const Duration(seconds: 5));
    expect(speech.starts, count);
    expect(voice.status, contains('Resume voice'));
    final stopping = voice.stop();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    await stopping;
    await speech.results.close();
    await speech.errors.close();
  });
}

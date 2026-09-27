import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:visionnav_app/services/navigation_service.dart';
import 'package:visionnav_app/services/service_interfaces.dart';
import 'package:visionnav_app/services/voice_destination_session.dart';

class _FakeTts implements TtsService {
  final spoken = <String>[];

  @override
  Future<void> speak(String text) async => spoken.add(text);

  @override
  Future<void> stop() async {}
}

class _FakeSpeech implements SpeechRecognitionService {
  final controller = StreamController<String>.broadcast();
  bool listening = false;
  int startCount = 0;

  @override
  Stream<String> get textStream => controller.stream;

  @override
  Future<void> startListening() async {
    listening = true;
    startCount += 1;
  }

  @override
  Future<void> stopListening() async {
    listening = false;
  }
}

class _FakeLocation implements LocationService {
  @override
  Future<bool> requestPermissions() async => true;

  @override
  Stream<Map<String, double>> get locationStream => const Stream.empty();
}

void main() {
  late _FakeTts tts;
  late _FakeSpeech speech;
  late BasicNavigationService nav;
  late List<String> spokenWait;
  late VoiceDestinationSession session;

  setUp(() {
    tts = _FakeTts();
    speech = _FakeSpeech();
    nav = BasicNavigationService(_FakeLocation());
    spokenWait = <String>[];
    session = VoiceDestinationSession(
      tts: tts,
      speech: speech,
      navigation: nav,
      listenGap: Duration.zero,
      speakAndWait: (text) async => spokenWait.add(text),
    );
  });

  tearDown(() async {
    await session.dispose();
    await speech.controller.close();
    await nav.dispose();
  });

  test('begin asks the prompt then starts listening', () async {
    await session.begin();
    expect(spokenWait, [VoiceDestinationSession.promptPhrase]);
    expect(speech.startCount, 1);
    expect(speech.listening, isTrue);
    expect(session.phase, VoiceDestinationPhase.listening);
  });

  test('recognized speech is stored, shown, and spoken back', () async {
    await session.begin();
    speech.controller.add('central bus stand');
    await Future<void>.delayed(Duration.zero);

    expect(session.destination, 'central bus stand');
    expect(nav.destination, 'central bus stand');
    expect(session.liveTranscript, 'central bus stand');
    expect(session.phase, VoiceDestinationPhase.done);
    expect(spokenWait.last, 'Destination set to central bus stand');
    expect(speech.listening, isFalse);
  });

  test('empty speech does not set a destination', () async {
    await session.begin();
    speech.controller.add('   ');
    await Future<void>.delayed(Duration.zero);

    expect(session.destination, isNull);
    expect(nav.destination, isNull);
    expect(session.phase, VoiceDestinationPhase.listening);
  });

  test('a second utterance is ignored after confirmation', () async {
    await session.begin();
    speech.controller.add('airport');
    await Future<void>.delayed(Duration.zero);
    speech.controller.add('railway station');
    await Future<void>.delayed(Duration.zero);

    expect(nav.destination, 'airport');
    expect(spokenWait.where((s) => s.startsWith('Destination set')).length, 1);
  });
}

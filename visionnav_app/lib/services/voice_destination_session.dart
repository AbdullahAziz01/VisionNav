import 'dart:async';

import 'package:visionnav_app/services/service_interfaces.dart';

enum VoiceDestinationPhase {
  idle,
  prompting,
  listening,
  confirming,
  done,
  failed,
}

/// Orchestrates: TTS prompt → listen → show destination → speak confirmation.
///
/// No routing. Pure session logic so it can be unit-tested with fakes.
class VoiceDestinationSession {
  VoiceDestinationSession({
    required this.tts,
    required this.speech,
    required this.navigation,
    required this.speakAndWait,
    Stream<String>? confirmedUtterances,
    Stream<void>? listenEnded,
    this.listenGap = const Duration(milliseconds: 400),
    this.onChanged,
  }) {
    _liveSub = speech.textStream.listen((text) {
      liveTranscript = text;
      onChanged?.call();
    });
    _finalSub = (confirmedUtterances ?? speech.textStream).listen(_onUtterance);
    _endedSub = listenEnded?.listen((_) => _onListenEnded());
  }

  static const promptPhrase = 'Where would you like to go?';

  final TtsService tts;
  final SpeechRecognitionService speech;
  final NavigationService navigation;
  final Future<void> Function(String text) speakAndWait;
  final Duration listenGap;
  final void Function()? onChanged;

  VoiceDestinationPhase phase = VoiceDestinationPhase.idle;
  String liveTranscript = '';
  String? destination;
  String? errorMessage;

  StreamSubscription<String>? _liveSub;
  StreamSubscription<String>? _finalSub;
  StreamSubscription<void>? _endedSub;
  bool _confirmed = false;
  bool _busy = false;

  Future<void> begin() async {
    if (_busy) return;
    _busy = true;
    _confirmed = false;
    destination = null;
    liveTranscript = '';
    errorMessage = null;
    phase = VoiceDestinationPhase.prompting;
    onChanged?.call();
    try {
      await speech.stopListening();
      await tts.stop();
      await speakAndWait(promptPhrase);
      if (listenGap > Duration.zero) {
        await Future<void>.delayed(listenGap);
      }
      phase = VoiceDestinationPhase.listening;
      onChanged?.call();
      await speech.startListening();
    } catch (e) {
      phase = VoiceDestinationPhase.failed;
      errorMessage = e.toString();
      onChanged?.call();
    } finally {
      _busy = false;
    }
  }

  Future<void> _onUtterance(String text) async {
    final dest = text.trim();
    if (dest.isEmpty || _confirmed) return;
    if (phase != VoiceDestinationPhase.listening) return;
    _confirmed = true;
    destination = dest;
    phase = VoiceDestinationPhase.confirming;
    onChanged?.call();
    try {
      await speech.stopListening();
      await navigation.setDestination(dest);
      await speakAndWait('Destination set to $dest');
      phase = VoiceDestinationPhase.done;
    } catch (e) {
      phase = VoiceDestinationPhase.failed;
      errorMessage = e.toString();
    }
    onChanged?.call();
  }

  Future<void> _onListenEnded() async {
    if (_confirmed || phase != VoiceDestinationPhase.listening) return;
    phase = VoiceDestinationPhase.failed;
    errorMessage = 'I did not hear a destination.';
    onChanged?.call();
    try {
      await speakAndWait('I did not hear a destination. Please try again.');
    } catch (_) {}
  }

  Future<void> dispose() async {
    await _liveSub?.cancel();
    await _finalSub?.cancel();
    await _endedSub?.cancel();
    await speech.stopListening();
  }
}

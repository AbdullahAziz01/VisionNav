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
    this.prompt = promptPhrase,
    this.onChanged,
    this.onCommand,
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
  final String prompt;
  final void Function()? onChanged;
  final Future<bool> Function(String)? onCommand;

  VoiceDestinationPhase phase = VoiceDestinationPhase.idle;
  String liveTranscript = '';
  String? destination;
  String? errorMessage;

  StreamSubscription<String>? _liveSub;
  StreamSubscription<String>? _finalSub;
  StreamSubscription<void>? _endedSub;
  bool _confirmed = false;
  bool _busy = false;
  bool _disposed = false;
  int _generation = 0;

  Future<void> begin() async {
    if (_busy || _disposed) return;
    _busy = true;
    final generation = ++_generation;
    _confirmed = false;
    destination = null;
    liveTranscript = '';
    errorMessage = null;
    phase = VoiceDestinationPhase.prompting;
    onChanged?.call();
    try {
      await speech.stopListening();
      if (_disposed || generation != _generation) return;
      await tts.stop();
      if (_disposed || generation != _generation) return;
      await speakAndWait(prompt);
      if (listenGap > Duration.zero) {
        await Future<void>.delayed(listenGap);
      }
      if (_disposed || generation != _generation) return;
      phase = VoiceDestinationPhase.listening;
      onChanged?.call();
      await speech.startListening();
    } catch (e) {
      phase = VoiceDestinationPhase.failed;
      errorMessage = e.toString();
      onChanged?.call();
    } finally {
      if (generation == _generation) _busy = false;
    }
  }

  Future<void> _onUtterance(String text) async {
    if (_confirmed || phase != VoiceDestinationPhase.listening) return;
    if (onCommand != null && await onCommand!(text)) {
      if (_disposed) return;
      phase = VoiceDestinationPhase.idle;
      onChanged?.call();
      return;
    }
    await submitDestination(text);
  }

  Future<void> submitDestination(String text) async {
    final dest = text.trim();
    if (_disposed ||
        dest.isEmpty ||
        phase == VoiceDestinationPhase.confirming ||
        phase == VoiceDestinationPhase.prompting) {
      return;
    }
    _confirmed = true;
    destination = dest;
    phase = VoiceDestinationPhase.confirming;
    onChanged?.call();
    try {
      await speech.stopListening();
      if (_disposed) return;
      await navigation.setDestination(dest);
      if (_disposed) return;
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

  Future<void> cancel() async {
    _generation++;
    _busy = false;
    _confirmed = true;
    phase = VoiceDestinationPhase.idle;
    await speech.stopListening();
    if (!_disposed) onChanged?.call();
  }

  Future<void> dispose() async {
    _disposed = true;
    await _liveSub?.cancel();
    await _finalSub?.cancel();
    await _endedSub?.cancel();
    await speech.stopListening();
  }
}

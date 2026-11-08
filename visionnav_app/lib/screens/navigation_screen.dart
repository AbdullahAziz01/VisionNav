import 'dart:async';
import 'package:visionnav_app/services/voice_commands.dart';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/bus_trip.dart';
import 'package:visionnav_app/services/navigation/geo_utils.dart';
import 'package:visionnav_app/services/navigation/navigation_config.dart';
import 'package:visionnav_app/services/navigation/route_navigation_service.dart';
import 'package:visionnav_app/services/speech_recognition_service.dart';
import 'package:visionnav_app/services/tts_service.dart';
import 'package:visionnav_app/services/voice_destination_session.dart';

/// GPS navigation: speak a destination → route → spoken turn-by-turn guidance.
/// Navigation itself lives in [RouteNavigationService.instance] so it keeps
/// running when the user switches to the Vision tab.
class NavigationScreen extends StatefulWidget {
  const NavigationScreen({super.key, this.busTrip, this.onScanBus});

  final BusTrip? busTrip;
  final VoidCallback? onScanBus;

  @override
  State<NavigationScreen> createState() => _NavigationScreenState();
}

class _NavigationScreenState extends State<NavigationScreen>
    with WidgetsBindingObserver {
  final RouteNavigationService _nav = RouteNavigationService.instance;
  final FlutterTtsService _tts = FlutterTtsService.shared;
  final SpeechToTextService _speech = SpeechToTextService.shared;
  final _voice = VoiceCommands.shared;
  final MapController _map = MapController();
  late final VoiceDestinationSession _session;

  VoiceDestinationPhase _lastPhase = VoiceDestinationPhase.idle;
  bool _mapReady = false;
  bool _resumeDestination = false;
  bool _followUser = true;

  @override
  void initState() {
    super.initState();
    _voice.register(this, _handleVoice);
    WidgetsBinding.instance.addObserver(this);
    _voice.addListener(_onVoiceState);
    _session = VoiceDestinationSession(
      tts: _tts,
      speech: _speech,
      navigation: _nav,
      speakAndWait: _tts.speakAndWait,
      confirmedUtterances: _speech.finalResults,
      listenEnded: _speech.listenEnded,
      onChanged: _onSessionChanged,
      onCommand: (words) async {
        final c = normalizeCommand(words);
        if (!isGlobalVoiceCommand(c) || c == 'add location') return false;
        await _speech.cancelListening();
        _voice.release(this);
        if (c == 'stop listening' || c == 'pause voice commands') {
          await _voice.stop();
          return true;
        }
        return _voice.dispatch(words);
      },
      prompt: widget.busTrip == null
          ? VoiceDestinationSession.promptPhrase
          : 'Which bus stand would you like to walk to?',
    );
    _nav.snapshot.addListener(_onNavChanged);

    // Ask for a destination only if we are not already guiding the user.
    if (!_nav.isNavigating && _nav.current.state != NavState.arrived) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) unawaited(_beginDestination());
      });
    }
  }

  void _onVoiceState() {
    if (!_voice.enabled &&
        (_session.phase == VoiceDestinationPhase.listening ||
            _session.phase == VoiceDestinationPhase.prompting)) {
      unawaited(_session.cancel().whenComplete(() => _voice.release(this)));
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) {
      _resumeDestination =
          _session.phase == VoiceDestinationPhase.listening ||
          _session.phase == VoiceDestinationPhase.prompting;
      if (_resumeDestination) {
        unawaited(_session.cancel().whenComplete(() => _voice.release(this)));
      }
    } else if (state == AppLifecycleState.resumed && _resumeDestination) {
      _resumeDestination = false;
      if (mounted && ModalRoute.of(context)?.isCurrent == true) {
        unawaited(_beginDestination());
      }
    }
  }

  Future<void> _beginDestination() async {
    await _voice.hold(this);
    if (!mounted) {
      _voice.release(this);
      return;
    }
    await _session.begin();
  }

  Future<bool> _handleVoice(String words) async {
    if (!mounted || ModalRoute.of(context)?.isCurrent != true) return false;
    final c = normalizeCommand(words);
    if (['add location', 'destination', 'change destination'].contains(c)) {
      unawaited(_beginDestination());
    } else if (c == 'stop navigation' || c == 'stop') {
      await _nav.stopNavigation();
      await _voice.say('Navigation stopped.');
    } else if (c == 'start navigation' || c == 'start') {
      if (_nav.current.place == null) {
        await _voice.say('First say add location to choose your destination.');
      } else {
        await _startNavigation();
      }
    } else if (c == 'repeat instruction' || c == 'repeat') {
      await _nav.repeatInstruction();
    } else if (c == 'recenter' || c == 're centre' || c == 'my location') {
      setState(() => _followUser = true);
      final p = _nav.current.position;
      if (p != null && _mapReady) _map.move(p, 17);
      await _voice.say(
        p == null
            ? 'Waiting for your GPS location.'
            : 'Map centered on your location.',
      );
    } else if (c == 'screen commands') {
      await _voice.say(
        'Say add location, start navigation, stop navigation, repeat instruction, my location, or scan bus.',
      );
    } else {
      return false;
    }
    return true;
  }

  void _onSessionChanged() {
    if (!mounted) return;
    setState(() {});
    if (_session.phase == VoiceDestinationPhase.done ||
        _session.phase == VoiceDestinationPhase.failed) {
      _voice.release(this);
    }
    // Destination recognised and geocoded → start guidance automatically.
    if (_session.phase == VoiceDestinationPhase.done &&
        _lastPhase != VoiceDestinationPhase.done &&
        _nav.current.state == NavState.ready) {
      unawaited(_startNavigation());
    }
    _lastPhase = _session.phase;
  }

  void _onNavChanged() {
    if (!mounted) return;
    setState(() {});
    final pos = _nav.current.position;
    if (_mapReady && _followUser && pos != null) {
      _map.move(pos, _map.camera.zoom < 15 ? 17 : _map.camera.zoom);
    }
  }

  Future<void> _startNavigation() async {
    try {
      await _nav.startNavigation();
      final route = _nav.current.route;
      if (route != null && _mapReady) {
        _map.fitCamera(
          CameraFit.coordinates(
            coordinates: route.geometry,
            padding: const EdgeInsets.all(48),
          ),
        );
      }
    } catch (_) {
      // Error already spoken + shown via snapshot.
    }
  }

  Future<void> _typeBusStand() async {
    await _session.cancel();
    await _voice.hold(this);
    if (!mounted) {
      _voice.release(this);
      return;
    }
    var text = '';
    final stand = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
          widget.busTrip == null
              ? 'Enter your destination'
              : 'Enter your bus stand',
        ),
        content: TextField(
          autofocus: true,
          decoration: InputDecoration(
            labelText: widget.busTrip == null
                ? 'Destination'
                : 'Bus stand name',
          ),
          textInputAction: TextInputAction.go,
          onChanged: (value) => text = value,
          onSubmitted: (value) => Navigator.pop(context, value),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, text),
            child: const Text('Use this stop'),
          ),
        ],
      ),
    );
    _voice.release(this);
    if (!mounted || stand == null || stand.trim().isEmpty) return;
    // A voice result may have started guidance while the dialog was open.
    if (_nav.isNavigating || _nav.current.state == NavState.routing) return;
    await _session.submitDestination(stand);
  }

  @override
  void dispose() {
    _nav.snapshot.removeListener(_onNavChanged);
    _voice.unregister(this);
    _voice.removeListener(_onVoiceState);
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_session.dispose().whenComplete(() => _voice.release(this)));
    _map.dispose();
    super.dispose();
  }

  // ── UI ─────────────────────────────────────────────────────────────────────

  String get _headline {
    final s = _nav.current;
    switch (s.state) {
      case NavState.geocoding:
        return 'Finding "${s.destinationText}"…';
      case NavState.ready:
        return 'Destination: ${s.place?.name ?? s.destinationText}';
      case NavState.routing:
        return 'Calculating walking route…';
      case NavState.navigating:
        return s.nextInstruction ?? s.currentInstruction ?? 'Navigating';
      case NavState.arrived:
        return 'Arrived at ${s.place?.name ?? 'destination'}';
      case NavState.error:
        return s.error ?? 'Navigation error';
      case NavState.idle:
        break;
    }
    switch (_session.phase) {
      case VoiceDestinationPhase.prompting:
        return 'Asking for destination…';
      case VoiceDestinationPhase.listening:
        return 'Listening… say your destination';
      case VoiceDestinationPhase.confirming:
        return 'Confirming…';
      case VoiceDestinationPhase.failed:
        return _session.errorMessage ?? 'Could not hear a destination';
      case VoiceDestinationPhase.idle:
      case VoiceDestinationPhase.done:
        return 'Tap the microphone and say where to go';
    }
  }

  Widget _instructionPanel() {
    final s = _nav.current;
    final navigating = s.state == NavState.navigating;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      color: Colors.black87,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                navigating ? Icons.turn_right : Icons.record_voice_over,
                color: Colors.tealAccent,
                size: 28,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  _headline,
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          if (navigating) ...[
            const SizedBox(height: 6),
            Text(
              'Next turn in ${GeoUtils.speakDistance(s.distanceToNextM)}  ·  '
              '${GeoUtils.speakDistance(s.remainingM)} remaining',
              style: const TextStyle(color: Colors.white70, fontSize: 14),
            ),
          ],
          if (_session.liveTranscript.isNotEmpty &&
              _session.phase == VoiceDestinationPhase.listening)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                'Heard: ${_session.liveTranscript}',
                style: const TextStyle(color: Colors.white70),
              ),
            ),
          if (s.lastSpoken != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                '🔊 ${s.lastSpoken}',
                style: const TextStyle(color: Colors.tealAccent, fontSize: 13),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          if (routingApiKey.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text(
                'Walking directions need an OpenRouteService key. Add it in Settings.',
                style: TextStyle(color: Colors.orangeAccent, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }

  Widget _mapView() {
    final s = _nav.current;
    final pos = s.position;
    final route = s.route;
    final dest = s.place?.location;
    final center =
        pos ?? dest ?? const LatLng(33.6844, 73.0479); // Islamabad fallback

    return FlutterMap(
      mapController: _map,
      options: MapOptions(
        initialCenter: center,
        initialZoom: pos != null ? 17 : 12,
        onMapReady: () {
          _mapReady = true;
          if (route != null) {
            _map.fitCamera(
              CameraFit.coordinates(
                coordinates: route.geometry,
                padding: const EdgeInsets.all(48),
              ),
            );
          }
        },
        onPositionChanged: (camera, hasGesture) {
          if (hasGesture && _followUser) setState(() => _followUser = false);
        },
      ),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.visionnav.visionnav_app',
        ),
        if (route != null)
          PolylineLayer(
            polylines: [
              Polyline(
                points: route.geometry,
                strokeWidth: 6,
                color: Colors.tealAccent,
              ),
            ],
          ),
        MarkerLayer(
          markers: [
            if (dest != null)
              Marker(
                point: dest,
                width: 40,
                height: 40,
                child: const Icon(
                  Icons.flag,
                  color: Colors.redAccent,
                  size: 36,
                ),
              ),
            if (pos != null)
              Marker(
                point: pos,
                width: 28,
                height: 28,
                child: Container(
                  decoration: BoxDecoration(
                    color: Colors.blueAccent,
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 3),
                  ),
                ),
              ),
          ],
        ),
        const RichAttributionWidget(
          attributions: [TextSourceAttribution('© OpenStreetMap contributors')],
        ),
      ],
    );
  }

  Widget _controls() {
    final s = _nav.current;
    final navigating = s.state == NavState.navigating;
    final busy =
        s.state == NavState.geocoding ||
        s.state == NavState.routing ||
        _session.phase == VoiceDestinationPhase.prompting;

    return Container(
      color: Colors.black87,
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 14),
      child: Row(
        children: [
          Expanded(
            child: ElevatedButton.icon(
              onPressed: busy ? null : () => unawaited(_beginDestination()),
              icon: const Icon(Icons.mic),
              label: const Text('Destination'),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: navigating
                ? ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.redAccent,
                    ),
                    onPressed: () => unawaited(_nav.stopNavigation()),
                    icon: const Icon(Icons.stop),
                    label: const Text('Stop'),
                  )
                : ElevatedButton.icon(
                    onPressed: (s.place == null || busy)
                        ? null
                        : () => unawaited(_startNavigation()),
                    icon: const Icon(Icons.navigation),
                    label: const Text('Start'),
                  ),
          ),
          const SizedBox(width: 8),
          IconButton.filledTonal(
            tooltip: 'Repeat instruction',
            onPressed: navigating
                ? () => unawaited(_nav.repeatInstruction())
                : null,
            icon: const Icon(Icons.replay),
          ),
          IconButton.filledTonal(
            tooltip: _followUser ? 'Following you' : 'Re-centre on me',
            onPressed: () {
              setState(() => _followUser = true);
              final p = _nav.current.position;
              if (p != null && _mapReady) _map.move(p, 17);
            },
            icon: Icon(
              _followUser ? Icons.my_location : Icons.location_searching,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = _nav.current.state;
    return Scaffold(
      appBar: AppBar(title: const Text('Navigation')),
      body: Column(
        children: [
          _instructionPanel(),
          Expanded(child: _mapView()),
          if (widget.busTrip case final trip?)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text('Selected bus: ${trip.label}'),
            ),
          if (state == NavState.idle || state == NavState.error)
            TextButton.icon(
              onPressed: _session.phase == VoiceDestinationPhase.prompting
                  ? null
                  : _typeBusStand,
              icon: const Icon(Icons.keyboard),
              label: Text(
                widget.busTrip == null
                    ? 'Type destination'
                    : 'Type bus stand name',
              ),
            ),
          if (widget.busTrip != null && state == NavState.arrived)
            FilledButton.icon(
              onPressed: widget.onScanBus,
              icon: const Icon(Icons.camera_alt),
              label: const Text('Scan for your bus'),
            ),
          _controls(),
        ],
      ),
    );
  }
}

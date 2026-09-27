import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
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
  const NavigationScreen({super.key});

  @override
  State<NavigationScreen> createState() => _NavigationScreenState();
}

class _NavigationScreenState extends State<NavigationScreen> {
  final RouteNavigationService _nav = RouteNavigationService.instance;
  final FlutterTtsService _tts = FlutterTtsService.shared;
  final SpeechToTextService _speech = SpeechToTextService();
  final MapController _map = MapController();
  late final VoiceDestinationSession _session;

  VoiceDestinationPhase _lastPhase = VoiceDestinationPhase.idle;
  bool _mapReady = false;
  bool _followUser = true;

  @override
  void initState() {
    super.initState();
    _session = VoiceDestinationSession(
      tts: _tts,
      speech: _speech,
      navigation: _nav,
      speakAndWait: _tts.speakAndWait,
      confirmedUtterances: _speech.finalResults,
      listenEnded: _speech.listenEnded,
      onChanged: _onSessionChanged,
    );
    _nav.snapshot.addListener(_onNavChanged);

    // Ask for a destination only if we are not already guiding the user.
    if (!_nav.isNavigating && _nav.current.state != NavState.arrived) {
      WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_session.begin()));
    }
  }

  void _onSessionChanged() {
    if (!mounted) return;
    setState(() {});
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

  @override
  void dispose() {
    _nav.snapshot.removeListener(_onNavChanged);
    unawaited(_session.dispose());
    unawaited(_speech.dispose());
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
                  style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
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
          if (kOrsApiKey.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text(
                'Routing key missing — set ORS_API_KEY (see navigation_config.dart).',
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
    final center = pos ?? dest ?? const LatLng(33.6844, 73.0479); // Islamabad fallback

    return FlutterMap(
      mapController: _map,
      options: MapOptions(
        initialCenter: center,
        initialZoom: pos != null ? 17 : 12,
        onMapReady: () {
          _mapReady = true;
          if (route != null) {
            _map.fitCamera(CameraFit.coordinates(
              coordinates: route.geometry,
              padding: const EdgeInsets.all(48),
            ));
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
              Polyline(points: route.geometry, strokeWidth: 6, color: Colors.tealAccent),
            ],
          ),
        MarkerLayer(
          markers: [
            if (dest != null)
              Marker(
                point: dest,
                width: 40,
                height: 40,
                child: const Icon(Icons.flag, color: Colors.redAccent, size: 36),
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
    final busy = s.state == NavState.geocoding ||
        s.state == NavState.routing ||
        _session.phase == VoiceDestinationPhase.prompting;

    return Container(
      color: Colors.black87,
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 14),
      child: Row(
        children: [
          Expanded(
            child: ElevatedButton.icon(
              onPressed: busy ? null : () => unawaited(_session.begin()),
              icon: const Icon(Icons.mic),
              label: const Text('Destination'),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: navigating
                ? ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(backgroundColor: Colors.redAccent),
                    onPressed: () => unawaited(_nav.stopNavigation()),
                    icon: const Icon(Icons.stop),
                    label: const Text('Stop'),
                  )
                : ElevatedButton.icon(
                    onPressed: (s.place == null || busy) ? null : () => unawaited(_startNavigation()),
                    icon: const Icon(Icons.navigation),
                    label: const Text('Start'),
                  ),
          ),
          const SizedBox(width: 8),
          IconButton.filledTonal(
            tooltip: 'Repeat instruction',
            onPressed: navigating ? () => unawaited(_nav.repeatInstruction()) : null,
            icon: const Icon(Icons.replay),
          ),
          IconButton.filledTonal(
            tooltip: _followUser ? 'Following you' : 'Re-centre on me',
            onPressed: () {
              setState(() => _followUser = true);
              final p = _nav.current.position;
              if (p != null && _mapReady) _map.move(p, 17);
            },
            icon: Icon(_followUser ? Icons.my_location : Icons.location_searching),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Navigation')),
      body: Column(
        children: [
          _instructionPanel(),
          Expanded(child: _mapView()),
          _controls(),
        ],
      ),
    );
  }
}

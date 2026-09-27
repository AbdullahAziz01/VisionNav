import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/location_service.dart';
import 'package:visionnav_app/services/navigation/geo_utils.dart';
import 'package:visionnav_app/services/navigation/geocoding_service.dart';
import 'package:visionnav_app/services/navigation/guidance_engine.dart';
import 'package:visionnav_app/services/navigation/route_models.dart';
import 'package:visionnav_app/services/navigation/routing_service.dart';
import 'package:visionnav_app/services/service_interfaces.dart';
import 'package:visionnav_app/services/tts_service.dart';

enum NavState { idle, geocoding, ready, routing, navigating, arrived, error }

/// Immutable view of navigation for the UI.
class NavigationSnapshot {
  const NavigationSnapshot({
    this.state = NavState.idle,
    this.destinationText,
    this.place,
    this.route,
    this.position,
    this.currentInstruction,
    this.nextInstruction,
    this.distanceToNextM = 0,
    this.remainingM = 0,
    this.lastSpoken,
    this.error,
  });

  final NavState state;
  final String? destinationText;
  final Place? place;
  final NavRoute? route;
  final LatLng? position;
  final String? currentInstruction;
  final String? nextInstruction;
  final double distanceToNextM;
  final double remainingM;
  final String? lastSpoken;
  final String? error;

  NavigationSnapshot copyWith({
    NavState? state,
    String? destinationText,
    Place? place,
    NavRoute? route,
    LatLng? position,
    String? currentInstruction,
    String? nextInstruction,
    double? distanceToNextM,
    double? remainingM,
    String? lastSpoken,
    String? error,
    bool clearError = false,
    bool clearRoute = false,
  }) {
    return NavigationSnapshot(
      state: state ?? this.state,
      destinationText: destinationText ?? this.destinationText,
      place: place ?? this.place,
      route: clearRoute ? null : (route ?? this.route),
      position: position ?? this.position,
      currentInstruction: currentInstruction ?? this.currentInstruction,
      nextInstruction: nextInstruction ?? this.nextInstruction,
      distanceToNextM: distanceToNextM ?? this.distanceToNextM,
      remainingM: remainingM ?? this.remainingM,
      lastSpoken: lastSpoken ?? this.lastSpoken,
      error: clearError ? null : (error ?? this.error),
    );
  }
}

/// Real GPS navigation: spoken destination → geocode → walking route →
/// turn-by-turn speech that follows the user's GPS position.
///
/// App-level singleton ([RouteNavigationService.instance]) so guidance keeps
/// running while the user is on the Vision tab hearing obstacle warnings.
class RouteNavigationService implements NavigationService {
  RouteNavigationService({
    required this.location,
    required this.currentPosition,
    required this.tts,
    required this.geocoder,
    required this.router,
    this.rerouteCooldown = const Duration(seconds: 20),
  });

  static RouteNavigationService? _instance;

  static RouteNavigationService get instance {
    if (_instance != null) return _instance!;
    final loc = GeolocatorLocationService(distanceFilterMeters: 3);
    final tts = FlutterTtsService.shared;
    unawaited(tts.initialize());
    _instance = RouteNavigationService(
      location: loc,
      currentPosition: () async {
        final m = await loc.getCurrentLocation();
        return LatLng(m['latitude']!, m['longitude']!);
      },
      tts: tts,
      geocoder: NominatimGeocodingService(),
      router: OrsRoutingService(),
    );
    return _instance!;
  }

  final LocationService location;
  final Future<LatLng> Function() currentPosition;
  final TtsService tts;
  final GeocodingService geocoder;
  final RoutingService router;
  final Duration rerouteCooldown;

  final ValueNotifier<NavigationSnapshot> snapshot =
      ValueNotifier<NavigationSnapshot>(const NavigationSnapshot());

  final StreamController<GuidanceEvent> _events = StreamController<GuidanceEvent>.broadcast();
  Stream<GuidanceEvent> get events => _events.stream;

  GuidanceEngine? _engine;
  StreamSubscription<Map<String, double>>? _posSub;
  DateTime? _lastRerouteAt;
  bool _rerouting = false;

  NavigationSnapshot get current => snapshot.value;
  bool get isNavigating => current.state == NavState.navigating;

  void _set(NavigationSnapshot s) => snapshot.value = s;

  Future<void> _say(String text) async {
    _set(current.copyWith(lastSpoken: text));
    await tts.speak(text);
  }

  // ── NavigationService ────────────────────────────────────────────────────

  /// Geocode the spoken destination. Does not start guidance.
  @override
  Future<void> setDestination(String destination) async {
    final text = destination.trim();
    if (text.isEmpty) throw StateError('Empty destination.');
    _set(current.copyWith(
      state: NavState.geocoding,
      destinationText: text,
      clearError: true,
      clearRoute: true,
    ));
    LatLng? near;
    try {
      near = await currentPosition();
    } catch (_) {
      near = null; // geocode without bias
    }
    try {
      final place = await geocoder.geocode(text, near: near);
      _set(current.copyWith(state: NavState.ready, place: place, position: near));
      debugPrint('Destination geocoded: $place');
    } catch (e) {
      _set(current.copyWith(state: NavState.error, error: e.toString()));
      await _say(e is GeocodingException ? e.message : 'I could not find that place.');
      rethrow;
    }
  }

  @override
  Future<void> startNavigation() async {
    final place = current.place;
    if (place == null) throw StateError('Set a destination before starting navigation.');
    if (!await location.requestPermissions()) {
      const msg = 'Location permission or GPS is off. Please enable it.';
      _set(current.copyWith(state: NavState.error, error: msg));
      await _say(msg);
      throw StateError(msg);
    }

    _set(current.copyWith(state: NavState.routing, clearError: true));
    try {
      final from = await currentPosition();
      final route = await router.walkingRoute(from, place);
      _installRoute(route, from);
      final start = _engine!.start();
      _emit(start);
      await _say(start.speech);
      _set(current.copyWith(state: NavState.navigating));
      _listen();
    } catch (e) {
      final msg = e is RoutingException ? e.message : 'Could not calculate a route: $e';
      _set(current.copyWith(state: NavState.error, error: msg));
      await _say(msg);
      rethrow;
    }
  }

  @override
  Future<void> stopNavigation() async {
    final wasActive = _posSub != null || _engine != null;
    await _posSub?.cancel();
    _posSub = null;
    _engine = null;
    _set(current.copyWith(state: NavState.idle, clearRoute: true, distanceToNextM: 0, remainingM: 0));
    if (wasActive) await _say('Navigation stopped.');
  }

  /// Speak the current instruction again (for a "Repeat" button / voice cmd).
  Future<void> repeatInstruction() async {
    final e = _engine;
    if (e == null) {
      await _say('Navigation is not running.');
      return;
    }
    final next = e.nextStep;
    if (next == null) {
      await _say('Continue for ${GeoUtils.speakDistance(e.distanceToNextM)} to your destination.');
      return;
    }
    await _say('In ${GeoUtils.speakDistance(e.distanceToNextM)}, '
        '${next.instruction[0].toLowerCase()}${next.instruction.substring(1)}.');
  }

  // ── Internals ────────────────────────────────────────────────────────────

  void _installRoute(NavRoute route, LatLng at) {
    _engine = GuidanceEngine(route);
    _set(current.copyWith(
      route: route,
      position: at,
      currentInstruction: route.steps.first.instruction,
      nextInstruction: route.steps.length > 1 ? route.steps[1].instruction : null,
      distanceToNextM: route.steps.first.distanceM,
      remainingM: route.distanceM,
    ));
  }

  void _listen() {
    _posSub?.cancel();
    _posSub = location.locationStream.listen(
      (m) {
        final lat = m['latitude'];
        final lon = m['longitude'];
        if (lat == null || lon == null) return;
        unawaited(_onPosition(LatLng(lat, lon)));
      },
      onError: (Object e) => debugPrint('GPS stream error: $e'),
    );
  }

  Future<void> _onPosition(LatLng pos) async {
    final engine = _engine;
    if (engine == null) return;

    final events = engine.update(pos);
    _set(current.copyWith(
      position: pos,
      currentInstruction: engine.currentInstruction.instruction,
      nextInstruction: engine.nextStep?.instruction,
      distanceToNextM: engine.distanceToNextM,
      remainingM: engine.remainingDistanceM,
    ));

    for (final ev in events) {
      _emit(ev);
      await _say(ev.speech);
      if (ev.type == GuidanceEventType.arrived) {
        await _posSub?.cancel();
        _posSub = null;
        _engine = null;
        _set(current.copyWith(state: NavState.arrived, distanceToNextM: 0, remainingM: 0));
        return;
      }
      if (ev.type == GuidanceEventType.offRoute) {
        unawaited(_reroute(pos));
      }
    }
  }

  Future<void> _reroute(LatLng from) async {
    if (_rerouting) return;
    final last = _lastRerouteAt;
    if (last != null && DateTime.now().difference(last) < rerouteCooldown) return;
    final place = current.place;
    if (place == null) return;

    _rerouting = true;
    _lastRerouteAt = DateTime.now();
    try {
      final route = await router.walkingRoute(from, place);
      if (_engine == null) return; // stopped meanwhile
      _installRoute(route, from);
      _engine!.start(); // prime internal state; speak a short version instead
      final first = route.steps.first;
      final buf = StringBuffer('Route updated. ${first.instruction}.');
      if (first.distanceM >= 30) {
        buf.write(' Continue for ${GeoUtils.speakDistance(first.distanceM)}.');
      }
      await _say(buf.toString());
    } catch (e) {
      debugPrint('Reroute failed: $e');
      await _say('Could not update the route. Continue carefully.');
    } finally {
      _rerouting = false;
    }
  }

  void _emit(GuidanceEvent ev) {
    if (!_events.isClosed) _events.add(ev);
  }

  Future<void> dispose() async {
    await _posSub?.cancel();
    await _events.close();
    snapshot.dispose();
  }
}

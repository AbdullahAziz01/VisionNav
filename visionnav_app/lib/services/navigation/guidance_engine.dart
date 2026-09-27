import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/navigation/geo_utils.dart';
import 'package:visionnav_app/services/navigation/route_models.dart';

enum GuidanceEventType {
  start,
  approach, // "In 40 metres, turn left onto X"
  instruction, // "Turn left onto X" (at the corner)
  progress, // "Continue straight for 300 metres"
  offRoute, // "You are off the route. Recalculating."
  arrived,
}

class GuidanceEvent {
  const GuidanceEvent({
    required this.type,
    required this.speech,
    required this.stepIndex,
    required this.distanceToNextM,
  });

  final GuidanceEventType type;
  final String speech;
  final int stepIndex;
  final double distanceToNextM;

  @override
  String toString() => '${type.name}: $speech';
}

/// Turn-by-turn state machine. Pure Dart, no platform code, unit-testable.
///
/// Feed GPS positions to [update]; it returns zero or more events to speak.
/// The engine never speaks itself — the caller owns TTS.
class GuidanceEngine {
  GuidanceEngine(
    this.route, {
    this.approachDistanceM = 40,
    this.maneuverRadiusM = 12,
    this.arrivalRadiusM = 15,
    this.offRouteThresholdM = 35,
    this.offRouteConsecutive = 3,
    this.progressIntervalM = 150,
  });

  final NavRoute route;
  final double approachDistanceM;
  final double maneuverRadiusM;
  final double arrivalRadiusM;
  final double offRouteThresholdM;
  final int offRouteConsecutive;
  final double progressIntervalM;

  /// Index of the step the user is currently walking along.
  int currentStep = 0;
  bool arrived = false;
  bool offRoute = false;

  bool _preAnnounced = false;
  int _offRouteCount = 0;
  LatLng? _lastProgressPos;
  double _distanceToNextM = 0;

  /// Distance to the next manoeuvre (or destination) after the last update.
  double get distanceToNextM => _distanceToNextM;

  /// Instruction the user should be preparing for.
  RouteStep? get nextStep {
    final n = currentStep + 1;
    return n < route.steps.length ? route.steps[n] : null;
  }

  RouteStep get currentInstruction => route.steps[currentStep];

  /// Remaining distance along the route from the next manoeuvre onward.
  double get remainingDistanceM {
    var total = _distanceToNextM;
    for (var i = currentStep + 1; i < route.steps.length; i++) {
      total += route.steps[i].distanceM;
    }
    return total;
  }

  /// Call once when navigation begins.
  GuidanceEvent start() {
    final first = route.steps.isNotEmpty ? route.steps.first : null;
    final buf = StringBuffer(
      'Starting navigation to ${route.destination.name}. '
      '${GeoUtils.speakDistance(route.distanceM)}, '
      '${GeoUtils.speakDuration(route.durationS)}.',
    );
    if (first != null) {
      buf.write(' ${first.instruction}.');
      if (first.distanceM >= 30) {
        buf.write(' Continue for ${GeoUtils.speakDistance(first.distanceM)}.');
      }
    }
    _lastProgressPos = route.start;
    _distanceToNextM = first?.distanceM ?? route.distanceM;
    return GuidanceEvent(
      type: GuidanceEventType.start,
      speech: buf.toString(),
      stepIndex: 0,
      distanceToNextM: _distanceToNextM,
    );
  }

  /// Process a GPS fix. Returns events to speak (usually 0 or 1).
  List<GuidanceEvent> update(LatLng pos) {
    if (arrived || route.steps.isEmpty) return const [];
    final events = <GuidanceEvent>[];

    // ── Arrival ────────────────────────────────────────────────────────────
    final toEnd = GeoUtils.distanceM(pos, route.end);
    if (toEnd <= arrivalRadiusM) {
      arrived = true;
      _distanceToNextM = 0;
      events.add(GuidanceEvent(
        type: GuidanceEventType.arrived,
        speech: 'You have arrived at ${route.destination.name}.',
        stepIndex: route.steps.length - 1,
        distanceToNextM: 0,
      ));
      return events;
    }

    // ── Off-route detection ────────────────────────────────────────────────
    final onRoute = GeoUtils.distanceToPolyline(pos, route.geometry);
    if (onRoute.distanceM > offRouteThresholdM) {
      _offRouteCount++;
      if (_offRouteCount >= offRouteConsecutive && !offRoute) {
        offRoute = true;
        events.add(GuidanceEvent(
          type: GuidanceEventType.offRoute,
          speech: 'You seem to be off the route. Recalculating.',
          stepIndex: currentStep,
          distanceToNextM: _distanceToNextM,
        ));
      }
      return events;
    }
    _offRouteCount = 0;
    offRoute = false;

    // ── Next manoeuvre ─────────────────────────────────────────────────────
    final next = nextStep;
    if (next == null) {
      _distanceToNextM = toEnd;
      return events;
    }
    final dNext = GeoUtils.distanceM(pos, next.location);
    _distanceToNextM = dNext;

    // Reached the corner, or GPS shows we're already on the next step's path.
    final passedIntoNext = onRoute.segmentIndex >= next.startIndex && !next.isArrival;
    if (!next.isArrival && (dNext <= maneuverRadiusM || passedIntoNext)) {
      currentStep += 1;
      _preAnnounced = false;
      _lastProgressPos = pos;
      final buf = StringBuffer('${next.instruction}.');
      if (next.distanceM >= 30) {
        buf.write(' Continue for ${GeoUtils.speakDistance(next.distanceM)}.');
      }
      final after = nextStep;
      _distanceToNextM = after != null ? GeoUtils.distanceM(pos, after.location) : toEnd;
      events.add(GuidanceEvent(
        type: GuidanceEventType.instruction,
        speech: buf.toString(),
        stepIndex: currentStep,
        distanceToNextM: _distanceToNextM,
      ));
      return events;
    }

    // Warn shortly before the corner.
    if (!_preAnnounced && dNext <= approachDistanceM && !next.isArrival) {
      _preAnnounced = true;
      events.add(GuidanceEvent(
        type: GuidanceEventType.approach,
        speech: 'In ${GeoUtils.speakDistance(dNext)}, ${_lowerFirst(next.instruction)}.',
        stepIndex: currentStep,
        distanceToNextM: dNext,
      ));
      return events;
    }

    // Periodic reassurance on long straight stretches.
    final last = _lastProgressPos;
    if (last != null &&
        dNext > approachDistanceM &&
        GeoUtils.distanceM(last, pos) >= progressIntervalM) {
      _lastProgressPos = pos;
      final what = next.isArrival
          ? 'your destination'
          : _lowerFirst(next.instruction);
      events.add(GuidanceEvent(
        type: GuidanceEventType.progress,
        speech: 'Continue for ${GeoUtils.speakDistance(dNext)}, then $what.',
        stepIndex: currentStep,
        distanceToNextM: dNext,
      ));
    }
    return events;
  }

  static String _lowerFirst(String s) =>
      s.isEmpty ? s : s[0].toLowerCase() + s.substring(1);
}

import 'package:visionnav_app/services/pipeline_models.dart';

/// Decides WHAT to announce and WHEN, so the user is not flooded with speech.
///
/// Rules (all pure Dart, no platform code, unit-testable):
///  * At most one phrase per call.
///  * An obstacle within [closeRangeM] is spoken before a bus route. Those
///    urgent warnings may bypass the normal per-track cooldown and the global
///    gap, but only [maxUrgentRepeats] times per close-range stay, with at
///    least [urgentRepeatGap] between them.
///  * A stable bus route that loses to an urgent warning stays pending and can
///    be spoken afterward. A route is spoken once per track, route, and
///    direction state while that bus is still in the latest detections.
///    Route-only speech (no direction yet) is its own state. A later confirmed
///    direction is spoken once more. The phrase is the server's
///    route_tts_message.
///  * Otherwise the nearest qualifying distance phrase wins.
///  * A track is announced the first time it is seen with a distance.
///  * The same track is re-announced only when BOTH
///      - its per-track cooldown has elapsed, and
///      - its distance changed by at least [distanceChangeThresholdM]
///        (or it crossed into the [closeRangeM] zone).
///  * A global minimum gap keeps non-urgent announcements from overlapping.
///  * Tracks not seen for [trackExpiry] are forgotten, so a person who walks
///    away and comes back is announced again.
class AnnouncementManager {
  AnnouncementManager({
    this.perTrackCooldown = const Duration(seconds: 5),
    this.globalMinGap = const Duration(milliseconds: 2500),
    this.distanceChangeThresholdM = 1.0,
    this.closeRangeM = 1.5,
    this.urgentRepeatGap = const Duration(milliseconds: 1500),
    this.maxUrgentRepeats = 2,
    this.trackExpiry = const Duration(seconds: 10),
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  final Duration perTrackCooldown;
  final Duration globalMinGap;
  final double distanceChangeThresholdM;
  final double closeRangeM;
  final Duration urgentRepeatGap;
  final int maxUrgentRepeats;
  final Duration trackExpiry;
  final DateTime Function() _now;

  final Map<int, _TrackState> _tracks = {};
  final Set<_RouteAnnouncementKey> _announcedRoutes = {};
  DateTime? _lastAnnouncementAt;

  /// Feed the latest pipeline objects. Returns a phrase to speak, or null.
  ///
  /// Always updates internal state (last-seen, pruning). Only returns a phrase
  /// when [canSpeak] is true, so callers can pass `!tts.isSpeaking` and no
  /// announcement is "consumed" while the engine is busy.
  String? next(List<TrackedDetection> objects, {bool canSpeak = true}) {
    final now = _now();
    _prune(now);
    _forgetAbsentRoutes(objects);

    for (final obj in objects) {
      final state = _tracks.putIfAbsent(obj.trackId, _TrackState.new);
      state.lastSeen = now;
      final distance = obj.estimatedDistanceM;
      if (distance == null || distance > closeRangeM) {
        state.urgentCount = 0;
        state.lastUrgentAt = null;
      }
    }

    if (!canSpeak) return null;

    final urgent = _nextUrgent(objects, now);
    if (urgent != null) {
      return _speakDistance(urgent, now, urgent: true);
    }

    if (_lastAnnouncementAt != null &&
        now.difference(_lastAnnouncementAt!) < globalMinGap) {
      return null;
    }

    final route = _nextStableRoute(objects);
    if (route != null) {
      _announcedRoutes.add(_routeKey(route));
      _lastAnnouncementAt = now;
      return route.routeTtsMessage;
    }

    final candidates = objects
        .where((o) => o.estimatedDistanceM != null && o.estimatedDistanceM! > 0)
        .toList()
      ..sort((a, b) => a.estimatedDistanceM!.compareTo(b.estimatedDistanceM!));

    for (final obj in candidates) {
      final d = obj.estimatedDistanceM!;
      final state = _tracks[obj.trackId]!;
      if (!_qualifies(state, d, now)) continue;
      return _speakDistance(obj, now);
    }
    return null;
  }

  String _speakDistance(
    TrackedDetection obj,
    DateTime now, {
    bool urgent = false,
  }) {
    final d = obj.estimatedDistanceM!;
    final state = _tracks[obj.trackId]!;
    state.lastAnnouncedAt = now;
    state.lastAnnouncedDistance = d;
    if (urgent) {
      state.lastUrgentAt = now;
      state.urgentCount++;
    }
    _lastAnnouncementAt = now;
    return describe(obj.className, d);
  }

  TrackedDetection? _nextUrgent(
    List<TrackedDetection> objects,
    DateTime now,
  ) {
    final close = objects
        .where((o) {
          final d = o.estimatedDistanceM;
          return d != null && d > 0 && d <= closeRangeM;
        })
        .toList()
      ..sort((a, b) => a.estimatedDistanceM!.compareTo(b.estimatedDistanceM!));

    for (final obj in close) {
      if (_urgentQualifies(_tracks[obj.trackId]!, now)) return obj;
    }
    return null;
  }

  bool _urgentQualifies(_TrackState state, DateTime now) {
    if (state.urgentCount >= maxUrgentRepeats) return false;
    final lastUrgent = state.lastUrgentAt;
    if (lastUrgent == null) return true;
    return now.difference(lastUrgent) >= urgentRepeatGap;
  }

  TrackedDetection? _nextStableRoute(List<TrackedDetection> objects) {
    final eligible = objects.where((obj) {
      if (!_routeEligible(obj)) return false;
      return !_announcedRoutes.contains(_routeKey(obj));
    }).toList();
    if (eligible.isEmpty) return null;

    eligible.sort((a, b) {
      final aDistance = a.estimatedDistanceM;
      final bDistance = b.estimatedDistanceM;
      final aHasDistance = aDistance != null && aDistance > 0;
      final bHasDistance = bDistance != null && bDistance > 0;
      if (aHasDistance && bHasDistance) {
        return aDistance.compareTo(bDistance);
      }
      if (aHasDistance) return -1;
      if (bHasDistance) return 1;
      return a.trackId.compareTo(b.trackId);
    });
    return eligible.first;
  }

  bool _routeEligible(TrackedDetection obj) {
    if (obj.className != 'bus' || !obj.routeIsStable) return false;
    final message = obj.routeTtsMessage;
    return message != null && message.trim().isNotEmpty;
  }

  _RouteAnnouncementKey _routeKey(TrackedDetection obj) {
    final code = obj.routeCode;
    final route = code != null && code.trim().isNotEmpty
        ? code
        : (obj.routeLine ?? '');
    return _RouteAnnouncementKey(
      obj.trackId,
      route,
      obj.routeDirection ?? '',
    );
  }

  void _forgetAbsentRoutes(List<TrackedDetection> objects) {
    final liveIds = objects.map((obj) => obj.trackId).toSet();
    _announcedRoutes.removeWhere((key) => !liveIds.contains(key.trackId));
  }

  bool _qualifies(_TrackState state, double distance, DateTime now) {
    final lastAt = state.lastAnnouncedAt;
    final lastD = state.lastAnnouncedDistance;
    if (lastAt == null || lastD == null) return true; // never announced

    if (now.difference(lastAt) < perTrackCooldown) return false;

    final changedEnough = (distance - lastD).abs() >= distanceChangeThresholdM;
    final enteredCloseRange = distance <= closeRangeM && lastD > closeRangeM;
    return changedEnough || enteredCloseRange;
  }

  void _prune(DateTime now) {
    _tracks.removeWhere((_, s) => now.difference(s.lastSeen) > trackExpiry);
  }

  /// Forget everything (e.g. when the camera restarts).
  void reset() {
    _tracks.clear();
    _announcedRoutes.clear();
    _lastAnnouncementAt = null;
  }

  /// "Person approximately 3 meters away."
  static String describe(String className, double distanceM) {
    final name = _capitalize(className);
    if (distanceM < 1.0) return '$name less than 1 meter away.';

    // Round to the nearest 0.5 m; speaking "2.73 meters" is noise to a user.
    final rounded = (distanceM * 2).round() / 2;
    final String amount;
    if (rounded == rounded.roundToDouble()) {
      final whole = rounded.round();
      amount = whole == 1 ? '1 meter' : '$whole meters';
    } else {
      amount = '${rounded.toStringAsFixed(1)} meters';
    }
    return '$name approximately $amount away.';
  }

  static String _capitalize(String s) =>
      s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
}

class _TrackState {
  DateTime lastSeen = DateTime.fromMillisecondsSinceEpoch(0);
  DateTime? lastAnnouncedAt;
  double? lastAnnouncedDistance;
  DateTime? lastUrgentAt;
  int urgentCount = 0;
}

class _RouteAnnouncementKey {
  const _RouteAnnouncementKey(this.trackId, this.routeIdentity, this.routeDirection);

  final int trackId;
  final String routeIdentity;
  final String routeDirection;

  @override
  bool operator ==(Object other) {
    return other is _RouteAnnouncementKey &&
        other.trackId == trackId &&
        other.routeIdentity == routeIdentity &&
        other.routeDirection == routeDirection;
  }

  @override
  int get hashCode => Object.hash(trackId, routeIdentity, routeDirection);
}

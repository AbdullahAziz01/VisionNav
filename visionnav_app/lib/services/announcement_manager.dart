import 'package:visionnav_app/services/pipeline_models.dart';

/// Decides WHAT to announce and WHEN, so the user is not flooded with speech.
///
/// Rules (all pure Dart, no platform code, unit-testable):
///  * At most one phrase per call. A stable bus route is spoken before any
///    distance phrase. Otherwise the nearest qualifying object wins.
///  * A stable route is spoken once per track, line, and direction, and only
///    while that bus is still in the latest detections.
///  * A track is announced the first time it is seen with a distance.
///  * The same track is re-announced only when BOTH
///      - its per-track cooldown has elapsed, and
///      - its distance changed by at least [distanceChangeThresholdM]
///        (or it crossed into the [closeRangeM] zone).
///  * A global minimum gap keeps announcements from overlapping each other.
///  * Tracks not seen for [trackExpiry] are forgotten, so a person who walks
///    away and comes back is announced again.
class AnnouncementManager {
  AnnouncementManager({
    this.perTrackCooldown = const Duration(seconds: 5),
    this.globalMinGap = const Duration(milliseconds: 2500),
    this.distanceChangeThresholdM = 1.0,
    this.closeRangeM = 1.5,
    this.trackExpiry = const Duration(seconds: 10),
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  final Duration perTrackCooldown;
  final Duration globalMinGap;
  final double distanceChangeThresholdM;
  final double closeRangeM;
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
      _tracks.putIfAbsent(obj.trackId, _TrackState.new).lastSeen = now;
    }

    if (!canSpeak) return null;
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

      state.lastAnnouncedAt = now;
      state.lastAnnouncedDistance = d;
      _lastAnnouncementAt = now;
      return describe(obj.className, d);
    }
    return null;
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
    return _RouteAnnouncementKey(
      obj.trackId,
      obj.routeLine ?? '',
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
}

class _RouteAnnouncementKey {
  const _RouteAnnouncementKey(this.trackId, this.routeLine, this.routeDirection);

  final int trackId;
  final String routeLine;
  final String routeDirection;

  @override
  bool operator ==(Object other) {
    return other is _RouteAnnouncementKey &&
        other.trackId == trackId &&
        other.routeLine == routeLine &&
        other.routeDirection == routeDirection;
  }

  @override
  int get hashCode => Object.hash(trackId, routeLine, routeDirection);
}

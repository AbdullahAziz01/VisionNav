import 'dart:async';

import 'package:flutter_compass/flutter_compass.dart';
import 'package:geolocator/geolocator.dart';

/// One-shot device heading for approach-facing coaching.
///
/// Prefers magnetometer compass (works while standing still). Falls back to
/// GPS course-over-ground when the compass is unavailable.
class HeadingService {
  const HeadingService();

  /// Degrees clockwise from north, or null if unknown.
  Future<double?> currentHeadingDeg({
    Duration timeout = const Duration(seconds: 2),
  }) async {
    final compass = await _compassHeading(timeout);
    if (compass != null) return compass;
    return _gpsHeading();
  }

  Future<double?> _compassHeading(Duration timeout) async {
    final events = FlutterCompass.events;
    if (events == null) return null;
    try {
      final event = await events.first.timeout(timeout);
      final heading = event.heading;
      if (heading == null || heading.isNaN) return null;
      return (heading + 360) % 360;
    } on TimeoutException {
      return null;
    } catch (_) {
      return null;
    }
  }

  Future<double?> _gpsHeading() async {
    try {
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.best,
        ),
      );
      if (pos.heading < 0 || pos.heading.isNaN) return null;
      // GPS heading is unreliable when nearly stationary.
      if (pos.speed < 0.5) return null;
      return pos.heading % 360;
    } catch (_) {
      return null;
    }
  }
}

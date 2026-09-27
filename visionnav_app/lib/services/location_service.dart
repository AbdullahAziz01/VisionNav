import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'package:visionnav_app/services/service_interfaces.dart';

/// Thrown when location cannot be provided (service off or permission denied).
class LocationUnavailableException implements Exception {
  LocationUnavailableException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// GPS/location foundation built on the `geolocator` package.
///
/// This is intentionally minimal: permission handling, one-shot current
/// position, and a continuous position stream. Routing, maps and Lazarillo are
/// deliberately NOT here — they belong to NavigationService later.
///
/// Emitted map keys: `latitude`, `longitude`, `accuracy` (metres),
/// `heading` (degrees, -1 if unknown), `speed` (m/s).
class GeolocatorLocationService implements LocationService {
  GeolocatorLocationService({
    this.accuracy = LocationAccuracy.high,
    this.distanceFilterMeters = 5,
  });

  final LocationAccuracy accuracy;
  final int distanceFilterMeters;

  StreamController<Map<String, double>>? _controller;
  StreamSubscription<Position>? _positionSub;

  /// Ensures location services are on and permission is granted.
  /// Returns true if the app may access location.
  @override
  Future<bool> requestPermissions() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      debugPrint('Location services are disabled.');
      return false;
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      debugPrint('Location permission denied: $permission');
      return false;
    }
    return true; // whileInUse or always
  }

  /// One-shot current location. Throws [LocationUnavailableException] if the
  /// service/permission is not available.
  Future<Map<String, double>> getCurrentLocation() async {
    if (!await requestPermissions()) {
      throw LocationUnavailableException(
        'Location unavailable. Enable GPS and grant location permission.',
      );
    }
    final pos = await Geolocator.getCurrentPosition(
      locationSettings: LocationSettings(accuracy: accuracy),
    );
    return _toMap(pos);
  }

  /// Continuous location updates. Lazily starts the geolocator stream on first
  /// listen and cancels it when there are no listeners.
  @override
  Stream<Map<String, double>> get locationStream {
    _controller ??= StreamController<Map<String, double>>.broadcast(
      onListen: _startStream,
      onCancel: _stopStream,
    );
    return _controller!.stream;
  }

  void _startStream() {
    _positionSub?.cancel();
    final settings = LocationSettings(
      accuracy: accuracy,
      distanceFilter: distanceFilterMeters,
    );
    _positionSub = Geolocator.getPositionStream(locationSettings: settings)
        .listen((pos) => _controller?.add(_toMap(pos)),
            onError: (Object e) => _controller?.addError(e));
  }

  void _stopStream() {
    _positionSub?.cancel();
    _positionSub = null;
  }

  Map<String, double> _toMap(Position p) => {
        'latitude': p.latitude,
        'longitude': p.longitude,
        'accuracy': p.accuracy,
        'heading': p.heading,
        'speed': p.speed,
      };

  Future<void> dispose() async {
    await _positionSub?.cancel();
    await _controller?.close();
    _controller = null;
  }
}

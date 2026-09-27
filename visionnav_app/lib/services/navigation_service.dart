import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:visionnav_app/services/service_interfaces.dart';

/// High-level navigation state, exposed so the UI can react later.
enum NavigationStatus { idle, navigating }

/// Structural NavigationService for FUTURE routing (Lazarillo / maps / turn-by-turn).
///
/// This intentionally contains NO routing logic yet. It only:
///   * holds the current destination and navigation status,
///   * owns a reference to the LocationService so a router can be plugged in,
///   * exposes a status stream for the UI.
///
/// Routing, ETA, and turn-by-turn are TODOs to be implemented in the navigation
/// phase without changing this public surface.
class BasicNavigationService implements NavigationService {
  BasicNavigationService(this._location);

  final LocationService _location;

  final StreamController<NavigationStatus> _statusController =
      StreamController<NavigationStatus>.broadcast();

  String? _destination;
  NavigationStatus _status = NavigationStatus.idle;

  String? get destination => _destination;
  NavigationStatus get status => _status;
  Stream<NavigationStatus> get statusStream => _statusController.stream;

  /// Access to the location foundation for a future router.
  LocationService get location => _location;

  @override
  Future<void> setDestination(String destination) async {
    _destination = destination;
    debugPrint('Navigation destination set: $destination');
    // TODO(navigation phase): geocode destination -> lat/lng.
  }

  @override
  Future<void> startNavigation() async {
    if (_destination == null) {
      throw StateError('Set a destination before starting navigation.');
    }
    // Confirm we can actually get the user's position before "navigating".
    final ready = await _location.requestPermissions();
    if (!ready) {
      throw StateError('Location permission/service unavailable.');
    }
    _setStatus(NavigationStatus.navigating);
    // TODO(navigation phase): compute route, begin turn-by-turn guidance.
  }

  @override
  Future<void> stopNavigation() async {
    _setStatus(NavigationStatus.idle);
    // TODO(navigation phase): tear down active route/guidance.
  }

  void _setStatus(NavigationStatus status) {
    _status = status;
    _statusController.add(status);
  }

  Future<void> dispose() async {
    await _statusController.close();
  }
}

import 'package:latlong2/latlong.dart';

/// A geocoded place (result of turning spoken text into coordinates).
class Place {
  const Place({
    required this.name,
    required this.location,
    this.displayName,
  });

  /// Short label suitable for speech ("Saddar Bus Stand").
  final String name;

  /// Full address string from the geocoder (for the screen).
  final String? displayName;
  final LatLng location;

  @override
  String toString() => 'Place($name @ ${location.latitude},${location.longitude})';
}

/// One manoeuvre in a route. The [instruction] is performed at [location],
/// then the user walks [distanceM] along the route until the next step.
class RouteStep {
  const RouteStep({
    required this.instruction,
    required this.distanceM,
    required this.durationS,
    required this.location,
    required this.startIndex,
    required this.endIndex,
    this.streetName = '',
    this.type = -1,
  });

  final String instruction;
  final double distanceM;
  final double durationS;

  /// Where the manoeuvre happens (start of this step on the polyline).
  final LatLng location;

  /// Indices into [NavRoute.geometry] covered by this step.
  final int startIndex;
  final int endIndex;
  final String streetName;

  /// Provider-specific manoeuvre code (ORS: 0 left, 1 right, ... 10 arrive).
  final int type;

  bool get isArrival => type == 10 || instruction.toLowerCase().contains('arrive');
}

/// A computed walking route.
class NavRoute {
  const NavRoute({
    required this.geometry,
    required this.steps,
    required this.distanceM,
    required this.durationS,
    required this.destination,
  });

  final List<LatLng> geometry;
  final List<RouteStep> steps;
  final double distanceM;
  final double durationS;
  final Place destination;

  LatLng get start => geometry.first;
  LatLng get end => geometry.last;
}

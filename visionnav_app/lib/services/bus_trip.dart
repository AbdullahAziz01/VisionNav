import 'package:visionnav_app/services/pipeline_models.dart';

/// A bus and its signed direction, selected before walking to the stop.
class BusTrip {
  const BusTrip({
    required this.line,
    required this.code,
    required this.direction,
    required this.destination,
  });

  factory BusTrip.fromJson(Map<String, dynamic> json) => BusTrip(
    line: json['line'] as String,
    code: json['code'] as String?,
    direction: json['direction'] as String,
    destination: json['destination'] as String,
  );

  final String line;
  final String? code;
  final String direction;
  final String destination;

  String get label => '$line toward $destination';

  bool isSameRoute(TrackedDetection bus) => code == null
      ? bus.routeCode == null && bus.routeLine == line
      : bus.routeCode == code;

  bool matches(TrackedDetection bus) =>
      bus.className == 'bus' &&
      bus.routeIsStable &&
      isSameRoute(bus) &&
      bus.routeDirection == direction;

  String announcement(TrackedDetection bus) {
    final reading = bus.routeTtsMessage!;
    if (matches(bus)) return 'Your selected bus was detected. $reading';
    if (!isSameRoute(bus)) return 'Different bus. $reading';
    if (bus.routeDirection == null || bus.routeDirection!.isEmpty) {
      return reading;
    }
    return 'Your route, going in the other direction. $reading';
  }
}

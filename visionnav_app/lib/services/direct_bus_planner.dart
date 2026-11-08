import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/navigation/transit_gazetteer.dart';
import 'package:visionnav_app/services/bus_trip.dart';

class DirectBusPlan {
  const DirectBusPlan(
    this.route,
    this.toward,
    this.boarding,
    this.exit,
    this.departures,
    this.scanDirection,
    this.scanCode,
  );

  final String route;
  final String toward;
  final TransitStop boarding;
  final TransitStop exit;
  final List<Duration> departures;
  final String? scanDirection;
  final String? scanCode;

  BusTrip get scannerTrip => BusTrip(
    line: route,
    code: scanCode ?? route,
    direction: scanDirection,
    destination: toward,
    exitStop: exit.name,
  );

  /// CDA publishes Islamabad wall-clock times. Return an absolute UTC instant.
  DateTime? nextDeparture(
    DateTime now, {
    Duration timeToBoard = Duration.zero,
  }) {
    const offset = Duration(hours: 5);
    final localClock = now.toUtc().add(offset);
    final serviceDay = DateTime.utc(
      localClock.year,
      localClock.month,
      localClock.day,
    ).subtract(offset);
    final ready = now.add(timeToBoard);
    for (final time in departures) {
      final departure = serviceDay.add(time);
      if (!departure.isBefore(ready)) return departure;
    }
    return null;
  }

  String get summary =>
      'Suggested trip: $route toward $toward. Board at ${boarding.name}. '
      'Get off at ${exit.name}.';
}

/// Plans over ordered, directly served stops. Map locations are used for a
/// proximity estimate only; they are not direction-specific boarding pins.
class DirectBusPlanner {
  DirectBusPlanner._(this._directions);

  final List<
    ({
      String route,
      String toward,
      String? scanDirection,
      String? scanCode,
      List<String>? scanExitKeys,
      List<TransitStop> stops,
      Map<String, List<Duration>> departures,
    })
  >
  _directions;

  static Future<DirectBusPlanner> load() async {
    final raw = await rootBundle.loadString('assets/direct_bus_routes.json');
    final records =
        (jsonDecode(raw) as Map<String, dynamic>)['directions'] as List;
    final stops = {
      for (final stop in await TransitGazetteer().load()) stop.key: stop,
    };
    return DirectBusPlanner._([
      for (final record in records)
        (
          route: record['route'] as String,
          toward: record['toward'] as String,
          scanDirection: record['scanDirection'] as String?,
          scanCode: record['scanCode'] as String?,
          scanExitKeys: (record['scanExitKeys'] as List?)?.cast<String>(),
          departures: {
            for (final entry
                in (record['departures'] as Map<String, dynamic>? ?? {})
                    .entries)
              entry.key:
                  (entry.value as List).cast<String>().map(_parseTime).toList()
                    ..sort(),
          },
          stops: [
            for (final key in record['stopKeys'] as List)
              stops[key] ??
                  (throw FormatException('Unknown transit stop: $key')),
          ],
        ),
    ]);
  }

  static Duration _parseTime(String value) {
    final parts = value.split(':').map(int.parse).toList();
    return Duration(hours: parts[0], minutes: parts[1], seconds: parts[2]);
  }

  Set<String> get destinations => {
    for (final direction in _directions)
      for (final stop in direction.stops) stop.name,
  };

  String _key(String text) => TransitGazetteer.coreTokens(text).join(' ');

  bool _matches(TransitStop stop, String destination) =>
      _key(stop.name) == destination || stop.key == destination;

  bool serves(String destination) {
    final key = _key(destination);
    return key.isNotEmpty &&
        _directions.any(
          (direction) => direction.stops.any((stop) => _matches(stop, key)),
        );
  }

  DirectBusPlan? plan(String destination, LatLng origin) {
    final key = _key(destination);
    const distance = Distance();
    // Pilot coverage uses a straight-line radius, never a walking estimate.
    var nearestMeters = 1000.0;
    DirectBusPlan? best;
    for (final direction in _directions) {
      for (var i = 1; i < direction.stops.length; i++) {
        final exit = direction.stops[i];
        if (!_matches(exit, key)) continue;
        final exitMeters = distance(origin, exit.location);
        for (final boarding in direction.stops.take(i)) {
          final meters = distance(origin, boarding.location);
          if (meters >= nearestMeters || meters >= exitMeters) continue;
          nearestMeters = meters;
          best = DirectBusPlan(
            direction.route,
            direction.toward,
            boarding,
            exit,
            direction.departures[boarding.key] ?? const [],
            direction.scanExitKeys?.contains(exit.key) == false
                ? null
                : direction.scanDirection,
            direction.scanCode,
          );
        }
      }
    }
    return best;
  }
}

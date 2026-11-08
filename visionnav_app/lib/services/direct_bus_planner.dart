import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/navigation/transit_gazetteer.dart';
import 'package:visionnav_app/services/navigation/geo_utils.dart';
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
    this.boardingDistanceM,
  );

  final String route;
  final String toward;
  final TransitStop boarding;
  final TransitStop exit;
  final List<Duration> departures;
  final String? scanDirection;
  final String? scanCode;
  final double boardingDistanceM;

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
      'The boarding stop is about ${GeoUtils.speakDistance(boardingDistanceM)} away in a straight line. '
      'Get off at ${exit.name}.';
}

/// Plans over ordered, directly served stops. Map locations are used for a
/// proximity estimate only; they are not direction-specific boarding pins.
class DirectBusPlanner {
  DirectBusPlanner._(this._directions, this._publishedStops);

  final Set<String> _publishedStops;

  final List<
    ({
      String route,
      String toward,
      String? scanDirection,
      String? scanCode,
      List<String>? scanExitKeys,
      List<TransitStop> stops,
      Map<String, List<Duration>> departures,
      Map<String, String> aliases,
    })
  >
  _directions;

  static Future<DirectBusPlanner> load() async {
    final raw = await rootBundle.loadString('assets/direct_bus_routes.json');
    final data = jsonDecode(raw) as Map<String, dynamic>;
    final records = data['directions'] as List;
    final stops = {
      for (final stop in await TransitGazetteer().load()) stop.key: stop,
    };
    return DirectBusPlanner._(
      [
        for (final record in records)
          (
            route: record['route'] as String,
            toward: record['toward'] as String,
            scanDirection: record['scanDirection'] as String?,
            scanCode: record['scanCode'] as String?,
            aliases: (record['stopAliases'] as Map<String, dynamic>? ?? {})
                .cast<String, String>(),
            scanExitKeys: (record['scanExitKeys'] as List?)?.cast<String>(),
            departures: {
              for (final entry
                  in (record['departures'] as Map<String, dynamic>? ?? {})
                      .entries)
                entry.key:
                    (entry.value as List)
                        .cast<String>()
                        .map(_parseTime)
                        .toList()
                      ..sort(),
            },
            stops: [
              for (final key in record['stopKeys'] as List)
                stops[key] ??
                    (throw FormatException('Unknown transit stop: $key')),
            ],
          ),
      ],
      {
        for (final audit in data['coverage'] as List? ?? const [])
          for (final name
              in (audit['publishedStops'] as List? ?? const []).cast<String>())
            _key(name),
      },
    );
  }

  static Duration _parseTime(String value) {
    final parts = value.split(':').map(int.parse).toList();
    return Duration(hours: parts[0], minutes: parts[1], seconds: parts[2]);
  }

  int get routeCount =>
      _directions.map((direction) => direction.route).toSet().length;

  Set<String> get destinations => {
    for (final direction in _directions)
      for (final stop in direction.stops) stop.name,
  };

  static String _key(String text) =>
      TransitGazetteer.coreTokens(text).join(' ');

  bool _matches(
    TransitStop stop,
    String destination,
    Map<String, String> aliases,
  ) =>
      _key(stop.name) == destination ||
      stop.key == destination ||
      _key(aliases[stop.key] ?? '') == destination;

  bool listsStop(String destination) =>
      _publishedStops.contains(_key(destination));

  bool serves(String destination) {
    final key = _key(destination);
    return key.isNotEmpty &&
        _directions.any(
          (direction) => direction.stops.any(
            (stop) => _matches(stop, key, direction.aliases),
          ),
        );
  }

  DirectBusPlan? plan(String destination, LatLng origin, {DateTime? now}) {
    final key = _key(destination);
    if (key.isEmpty) return null;
    const distance = Distance();
    var bestMeters = double.infinity;
    var bestServiceRank = 3;
    DateTime? bestDeparture;
    DirectBusPlan? best;
    for (final direction in _directions) {
      for (var i = 1; i < direction.stops.length; i++) {
        final exit = direction.stops[i];
        if (!_matches(exit, key, direction.aliases)) continue;
        for (final boarding in direction.stops.take(i)) {
          final meters = distance(origin, boarding.location);
          final candidate = DirectBusPlan(
            direction.route,
            direction.toward,
            boarding,
            exit,
            direction.departures[boarding.key] ?? const [],
            direction.scanExitKeys?.contains(exit.key) == false
                ? null
                : direction.scanDirection,
            direction.scanCode,
            meters,
          );
          final departure = now == null ? null : candidate.nextDeparture(now);
          final serviceRank = now == null || departure != null
              ? 0
              : candidate.departures.isEmpty
              ? 1
              : 2;
          if (serviceRank > bestServiceRank) continue;
          if (serviceRank == bestServiceRank) {
            if (meters > bestMeters) continue;
            if (meters == bestMeters &&
                (departure == null ||
                    (bestDeparture != null &&
                        !departure.isBefore(bestDeparture)))) {
              continue;
            }
          }
          best = candidate;
          bestMeters = meters;
          bestServiceRank = serviceRank;
          bestDeparture = departure;
        }
      }
    }
    return best;
  }
}

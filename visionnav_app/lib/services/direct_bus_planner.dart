import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/navigation/approach_facing_coach.dart';
import 'package:visionnav_app/services/navigation/transit_gazetteer.dart';
import 'package:visionnav_app/services/navigation/geo_utils.dart';
import 'package:visionnav_app/services/bus_trip.dart';

DateTime _serviceDayStart(DateTime instant) {
  const offset = Duration(hours: 5);
  final local = instant.toUtc().add(offset);
  return DateTime.utc(local.year, local.month, local.day).subtract(offset);
}

class DirectBusPlan {
  const DirectBusPlan(
    this.route,
    this.toward,
    this.boarding,
    this.exit,
    this.departures,
    this.scanDirection,
    this.scanCode,
    this.boardingDistanceM, {
    this.boardingDistanceIsRoute = false,
    this.scheduledDeparture,
    this.scheduledArrivalAtExit,
    this.transferWalkDistanceM,
    this.terminalsOnly = false,
    this.travelBearingDeg,
    this.boardingCurbLocation,
    this.nextStopName,
  });

  final String route;
  final String toward;
  final TransitStop boarding;
  final TransitStop exit;
  final List<Duration> departures;
  final String? scanDirection;
  final String? scanCode;
  final double boardingDistanceM;
  final bool boardingDistanceIsRoute;
  final DateTime? scheduledDeparture;
  final DateTime? scheduledArrivalAtExit;
  final double? transferWalkDistanceM;
  final bool terminalsOnly;

  /// Bus travel bearing past the boarding stop (degrees), when known.
  final double? travelBearingDeg;

  /// Estimated kerb-side walk target (left of travel in Pakistan LHT).
  final LatLng? boardingCurbLocation;

  /// Next mapped stop after boarding on this direction (for speech).
  final String? nextStopName;

  static const maximumBoardingWalkM = 2000.0;

  /// Walk target for boarding guidance: curb estimate when available.
  LatLng get boardingWalkLocation => boardingCurbLocation ?? boarding.location;

  /// Where the bus comes from (opposite of travel). Face this for the camera.
  double? get approachBearingDeg =>
      travelBearingDeg == null ? null : (travelBearingDeg! + 180) % 360;

  BusTrip get scannerTrip => BusTrip(
    line: route,
    code: scanCode ?? route,
    direction: scanDirection,
    destination: toward,
    exitStop: exit.name,
  );

  DirectBusPlan withAccessDistance({
    required double distanceM,
    required bool isWalkingRoute,
    DateTime? departure,
    DateTime? arrivalAtExit,
  }) => DirectBusPlan(
    route,
    toward,
    boarding,
    exit,
    departures,
    scanDirection,
    scanCode,
    distanceM,
    boardingDistanceIsRoute: isWalkingRoute,
    scheduledDeparture: departure ?? scheduledDeparture,
    scheduledArrivalAtExit: arrivalAtExit ?? scheduledArrivalAtExit,
    transferWalkDistanceM: transferWalkDistanceM,
    terminalsOnly: terminalsOnly,
    travelBearingDeg: travelBearingDeg,
    boardingCurbLocation: boardingCurbLocation,
    nextStopName: nextStopName,
  );

  /// Spoken curb / roadside guidance. Uses route geometry + left-hand traffic.
  String get roadSideGuidanceSpeech {
    if (travelBearingDeg == null || boardingCurbLocation == null) {
      return 'Bus stands may exist on both sides of the road here. '
          'Ask stop staff which side serves $route toward $toward before you wait. '
          'Do not cross mid-block.';
    }
    final compass = GeoUtils.speakCompass(travelBearingDeg!);
    final next = nextStopName == null ? toward : nextStopName!;
    return 'Buses toward $toward leave this area heading $compass, next mapped stop $next. '
        'Pakistan drives on the left, so wait on the left-hand kerb when facing $compass — '
        'the side where doors open for buses going toward $toward. '
        'If you are on the opposite sidewalk, use a safe crossing. '
        'Confirm the side with stop staff; this kerb target is estimated from the route direction.';
  }

  /// Absolute approach-facing cue (no live compass). Prefer [facingCoachSpeech].
  String get approachFacingSpeech {
    final approach = approachBearingDeg;
    if (approach == null) {
      return 'When waiting, face so buses toward $toward approach in front of the camera, not from behind. '
          'Say check direction for live compass coaching.';
    }
    return ApproachFacingCoach.absoluteSpeech(
      approachBearingDeg: approach,
      toward: toward,
    );
  }

  /// Live facing coach using optional phone heading (degrees from north).
  String facingCoachSpeech({double? headingDeg}) {
    final approach = approachBearingDeg;
    if (approach == null) {
      return 'Route direction for facing is unavailable here. '
          'Ask stop staff which way buses toward $toward approach, and keep that way in front of the camera.';
    }
    return ApproachFacingCoach.speech(
      approachBearingDeg: approach,
      toward: toward,
      headingDeg: headingDeg,
    );
  }

  /// CDA publishes Islamabad wall-clock times. Return an absolute UTC instant.
  DateTime? nextDeparture(
    DateTime now, {
    Duration timeToBoard = Duration.zero,
  }) {
    if (departures.isEmpty) return null;
    final ready = now.add(timeToBoard);
    final serviceDay = _serviceDayStart(ready);
    for (final time in departures) {
      final departure = serviceDay.add(time);
      if (!departure.isBefore(ready)) return departure;
    }
    return null;
  }

  String get summary {
    final access = boardingDistanceIsRoute
        ? 'The walking route is ${GeoUtils.speakDistance(boardingDistanceM)}.'
        : 'The straight-line distance is about ${GeoUtils.speakDistance(boardingDistanceM)}; this is not walking distance.';
    final scope = terminalsOnly
        ? 'Only the published start and end terminals are mapped for this route; '
            'intermediate stops are not guided. Navigate to ${boarding.name} to board, '
            'then ride to ${exit.name}.'
        : 'Get off at ${exit.name}.';
    return 'Board $route toward $toward at ${boarding.name}. $access '
        '$scope $roadSideGuidanceSpeech';
  }

  /// Spoken scheduled wait. Never presented as a live GPS bus ETA.
  String scheduledWaitSpeech(DateTime now, {Duration timeToBoard = Duration.zero}) {
    final next = nextDeparture(now, timeToBoard: timeToBoard);
    if (next == null) {
      if (terminalsOnly && departures.isEmpty) {
        return '$route has no fixed published timetable. Wait at ${boarding.name} for a bus toward $toward. '
            'This is not a live bus location.';
      }
      return 'No more published departures are listed for $route at ${boarding.name} today. '
          'This is schedule data only, not a live bus location.';
    }
    final ready = now.add(timeToBoard);
    final minutes = (next.difference(ready).inSeconds / 60).ceil().clamp(0, 24 * 60);
    final clock = _formatIslamabadClock(next);
    final source = terminalsOnly
        ? 'CDA website headway estimate'
        : 'CDA schedule estimate';
    return 'The next published $route departure toward $toward from ${boarding.name} '
        'is at $clock, about $minutes minutes from now. '
        'This is a $source, not a live bus arrival.';
  }

  static String _formatIslamabadClock(DateTime time) {
    final clock = time.toUtc().add(const Duration(hours: 5));
    final hour = clock.hour % 12 == 0 ? 12 : clock.hour % 12;
    final minute = clock.minute.toString().padLeft(2, '0');
    final period = clock.hour < 12 ? 'AM' : 'PM';
    return '$hour:$minute $period Islamabad time';
  }
}

class TransitItinerary {
  const TransitItinerary(this.legs);

  final List<DirectBusPlan> legs;

  DirectBusPlan get firstLeg => legs.first;
  bool get hasTransfers => legs.length > 1;
  bool get timetableVerified =>
      legs.every((leg) => leg.scheduledDeparture != null);

  TransitItinerary withFirstLeg(DirectBusPlan firstLeg) =>
      TransitItinerary([firstLeg, ...legs.skip(1)]);

  String get summary {
    final parts = <String>[];
    for (var i = 0; i < legs.length; i++) {
      final leg = legs[i];
      parts.add(
        'Leg ${i + 1}: ${leg.route} toward ${leg.toward}. '
        'Board at ${leg.boarding.name}; get off at ${leg.exit.name}.',
      );
      if (i + 1 < legs.length) {
        final next = legs[i + 1];
        final transferDistance = next.transferWalkDistanceM ?? 0;
        final mappedDistance = transferDistance == 0
            ? 'co-located on the map'
            : '${GeoUtils.speakDistance(transferDistance)} apart';
        parts.add(
          'Transfer at ${leg.exit.name}; the mapped transfer points are '
          '$mappedDistance, '
          'but platform-side walking distance is unavailable.',
        );
      }
    }
    return parts.join(' ');
  }
}

class _RouteDirection {
  const _RouteDirection({
    required this.route,
    required this.toward,
    required this.scanDirection,
    required this.scanCode,
    required this.scanExitKeys,
    required this.stops,
    required this.departures,
    required this.aliases,
    required this.publishedStops,
    this.terminalsOnly = false,
  });

  final String route;
  final String toward;
  final String? scanDirection;
  final String? scanCode;
  final List<String>? scanExitKeys;
  final List<TransitStop> stops;
  final Map<String, List<Duration>> departures;
  final Map<String, String> aliases;
  final List<String> publishedStops;
  final bool terminalsOnly;
}

class _ScheduledDeparture {
  const _ScheduledDeparture(this.index, this.time);

  final int index;
  final DateTime time;
}

/// Plans only along ordered, published route directions. A route's mapped
/// terminal can be restored from its direction-specific CDA coverage when
/// the route record omitted a stop that is still in the published stop list.
class DirectBusPlanner {
  DirectBusPlanner._(this._directions, this._stopsByKey, this._publishedStops);

  final Set<String> _publishedStops;
  final Map<String, TransitStop> _stopsByKey;
  final List<_RouteDirection> _directions;

  static Future<DirectBusPlanner> load() async {
    final raw = await rootBundle.loadString('assets/direct_bus_routes.json');
    final data = jsonDecode(raw) as Map<String, dynamic>;
    final records = data['directions'] as List;
    final stops = {
      for (final stop in await TransitGazetteer().load()) stop.key: stop,
    };
    final coverageBySource = <String, List<String>>{
      for (final audit in data['coverage'] as List? ?? const [])
        if (audit['source'] case final String source)
          source: (audit['publishedStops'] as List? ?? const []).cast<String>(),
    };
    return DirectBusPlanner._(
      [
        for (final record in records)
          if ((record['verificationStatus'] as String?) != 'unverified_conflict')
            _RouteDirection(
              route: record['route'] as String,
              toward: record['toward'] as String,
              scanDirection: record['scanDirection'] as String?,
              scanCode: record['scanCode'] as String?,
              scanExitKeys: (record['scanExitKeys'] as List?)?.cast<String>(),
              aliases: (record['stopAliases'] as Map<String, dynamic>? ?? {})
                  .cast<String, String>(),
              publishedStops:
                  coverageBySource[record['source']] ?? const <String>[],
              terminalsOnly: record['terminalsOnly'] == true ||
                  (record['verificationStatus'] as String?) == 'index_terminals',
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
      stops,
      {
        for (final audit in data['coverage'] as List? ?? const [])
          if ((audit['verificationStatus'] as String?) != 'unverified_conflict')
            for (final name
                in (audit['publishedStops'] as List? ?? const [])
                    .cast<String>())
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

  static const _sectorNumbers = {
    'five': '5',
    'six': '6',
    'seven': '7',
    'eight': '8',
    'nine': '9',
    'ten': '10',
    'eleven': '11',
    'twelve': '12',
    'thirteen': '13',
    'fourteen': '14',
    'fifteen': '15',
    'sixteen': '16',
  };
  static final _sector = RegExp(
    r'\b([efghi])(?:\s*(\d{1,2})|\s+(' +
        _sectorNumbers.keys.join('|') +
        r'))\b',
  );

  static String _key(String text) => TransitGazetteer.coreTokens(text)
      .join(' ')
      .replaceAllMapped(_sector, (match) {
        final number = match[2] ?? _sectorNumbers[match[3]];
        return '${match[1]} $number';
      });

  static bool _phraseContains(String phrase, String query) {
    final phraseTokens = _key(
      phrase,
    ).split(' ').where((part) => part.isNotEmpty);
    final queryTokens = _key(query).split(' ').where((part) => part.isNotEmpty);
    return queryTokens.isNotEmpty && queryTokens.every(phraseTokens.contains);
  }

  bool _matches(
    TransitStop stop,
    String destination,
    _RouteDirection direction,
  ) {
    return _key(stop.name) == destination ||
        _key(stop.key) == destination ||
        _key(direction.aliases[stop.key] ?? '') == destination ||
        _coveredTerminal(direction, destination)?.key == stop.key;
  }

  TransitStop? _coveredTerminal(_RouteDirection direction, String destination) {
    if (!_phraseContains(direction.toward, destination)) return null;
    TransitStop? exact = _stopsByKey[destination];
    if (exact == null) {
      for (final stop in _stopsByKey.values) {
        if (_key(stop.name) == destination || _key(stop.key) == destination) {
          exact = stop;
          break;
        }
      }
    }
    for (final publishedName in direction.publishedStops) {
      if (_key(publishedName) != destination &&
          !_phraseContains(publishedName, destination)) {
        continue;
      }
      if (exact != null) return exact;
      for (final stop in _stopsByKey.values) {
        if (_key(stop.name) == destination || _key(stop.key) == destination) {
          return stop;
        }
      }
    }
    return exact;
  }

  List<TransitStop> _stopsForDestination(
    _RouteDirection direction,
    String destination,
  ) {
    final terminal = _coveredTerminal(direction, destination);
    if (terminal == null ||
        direction.stops.any((stop) => stop.key == terminal.key)) {
      return direction.stops;
    }
    return [...direction.stops, terminal];
  }

  bool listsStop(String destination) =>
      _publishedStops.contains(_key(destination));

  bool serves(String destination) {
    final key = _key(destination);
    return key.isNotEmpty &&
        _directions.any(
          (direction) => _stopsForDestination(
            direction,
            key,
          ).any((stop) => _matches(stop, key, direction)),
        );
  }

  /// Plans direct routes, and optionally searches up to three transfers at
  /// shared mapped stops with aligned timetable data.
  List<TransitItinerary> journeys(
    String destination,
    LatLng origin, {
    DateTime? now,
    Duration initialWalkDuration = Duration.zero,
    String? initialBoardingKey,
    bool includeTransfers = false,
  }) {
    final key = _key(destination);
    if (key.isEmpty) return const [];

    final direct = <TransitItinerary>[];
    for (final direction in _directions) {
      final stops = _stopsForDestination(direction, key);
      for (var exitIndex = 1; exitIndex < stops.length; exitIndex++) {
        final exit = stops[exitIndex];
        if (!_matches(exit, key, direction)) continue;
        for (var boardIndex = 0; boardIndex < exitIndex; boardIndex++) {
          final boarding = stops[boardIndex];
          if (initialBoardingKey != null &&
              boarding.key != initialBoardingKey) {
            continue;
          }
          final departures = direction.departures[boarding.key] ?? const [];
          final scheduled = now == null
              ? null
              : _nextScheduledDeparture(
                  departures,
                  now.add(initialWalkDuration),
                );
          if (now != null && (departures.isEmpty || scheduled == null)) {
            continue;
          }
          final arrival = scheduled == null
              ? null
              : _scheduledTimeAtStop(direction.departures[exit.key], scheduled);
          final leg = _makeLeg(
            direction,
            boarding,
            exit,
            origin,
            nextAlongRoute: stops[boardIndex + 1],
            scheduledDeparture: scheduled?.time,
            scheduledArrivalAtExit: arrival,
          );
          direct.add(TransitItinerary([leg]));
        }
      }
    }
    // Prefer a direct ride whenever one exists. With full-catalog terminals
    // coverage, expanding every headway into multi-transfer search is too
    // expensive for on-device planning and is unnecessary when a direct leg works.
    if (direct.isNotEmpty || !includeTransfers || now == null) {
      _sortItineraries(direct);
      return direct;
    }

    final starts = <String, TransitStop>{};
    for (final direction in _directions) {
      for (final stop in direction.stops) {
        if ((direction.departures[stop.key] ?? const []).isNotEmpty &&
            (initialBoardingKey == null || initialBoardingKey == stop.key)) {
          starts[stop.key] = stop;
        }
      }
    }
    final transfers = <TransitItinerary>[];
    final orderedStarts = starts.values.toList()
      ..sort(
        (a, b) => const Distance()(
          origin,
          a.location,
        ).compareTo(const Distance()(origin, b.location)),
      );
    for (final start in orderedStarts) {
      if (transfers.length >= 40) break;
      _searchTransfers(
        destination: key,
        origin: origin,
        now: now.add(initialWalkDuration),
        currentStopKey: start.key,
        legs: const [],
        usedRoutes: const {},
        visitedStops: {start.key},
        found: transfers,
        maxResults: 40 - transfers.length,
      );
    }
    direct.addAll(transfers);
    _sortItineraries(direct);
    return direct;
  }

  void _searchTransfers({
    required String destination,
    required LatLng origin,
    required DateTime now,
    required String currentStopKey,
    required List<DirectBusPlan> legs,
    required Set<String> usedRoutes,
    required Set<String> visitedStops,
    required List<TransitItinerary> found,
    required int maxResults,
  }) {
    if (legs.length >= 4 || found.length >= maxResults) return;
    for (final direction in _directions) {
      if (usedRoutes.contains(direction.route)) continue;
      final stops = _stopsForDestination(direction, destination);
      for (var boardIndex = 0; boardIndex < stops.length; boardIndex++) {
        final boarding = stops[boardIndex];
        if (boarding.key != currentStopKey) continue;
        final boardTimes = direction.departures[boarding.key];
        if (boardTimes == null || boardTimes.isEmpty) continue;
        final scheduledOptions = _scheduledDepartures(
          boardTimes,
          now,
          limit: 4,
        );
        for (final scheduled in scheduledOptions) {
          for (
            var exitIndex = boardIndex + 1;
            exitIndex < stops.length;
            exitIndex++
          ) {
            final exit = stops[exitIndex];
            if (visitedStops.contains(exit.key)) continue;
            final matchesDestination = _matches(exit, destination, direction);
            final exitTimes = direction.departures[exit.key];
            final aligned =
                exitTimes != null &&
                exitTimes.length == boardTimes.length &&
                scheduled.index < exitTimes.length;
            final arrival = aligned
                ? _timeOnServiceDay(scheduled.time, exitTimes[scheduled.index])
                : null;
            if (!matchesDestination && arrival == null) continue;

            final leg = _makeLeg(
              direction,
              boarding,
              exit,
              origin,
              nextAlongRoute: stops[boardIndex + 1],
              scheduledDeparture: scheduled.time,
              scheduledArrivalAtExit: arrival,
              transferWalkDistanceM: legs.isEmpty ? null : 0,
            );
            final path = [...legs, leg];
            if (matchesDestination) {
              found.add(TransitItinerary(path));
              continue;
            }
            if (arrival == null || found.length >= maxResults) continue;
            _searchTransfers(
              destination: destination,
              origin: origin,
              now: arrival.add(const Duration(seconds: 1)),
              currentStopKey: exit.key,
              legs: path,
              usedRoutes: {...usedRoutes, direction.route},
              visitedStops: {...visitedStops, exit.key},
              found: found,
              maxResults: maxResults,
            );
          }
        }
      }
    }
  }

  DirectBusPlan _makeLeg(
    _RouteDirection direction,
    TransitStop boarding,
    TransitStop exit,
    LatLng origin, {
    TransitStop? nextAlongRoute,
    DateTime? scheduledDeparture,
    DateTime? scheduledArrivalAtExit,
    double? transferWalkDistanceM,
  }) {
    final next = nextAlongRoute ?? exit;
    final travelBearing = GeoUtils.distanceM(boarding.location, next.location) >= 5
        ? GeoUtils.bearingDeg(boarding.location, next.location)
        : null;
    final curb = travelBearing == null
        ? null
        : GeoUtils.estimatedBoardingCurb(
            stop: boarding.location,
            nextAlongRoute: next.location,
          );
    final walkTarget = curb ?? boarding.location;
    final meters = const Distance()(origin, walkTarget);
    final scanDirection = direction.scanExitKeys?.contains(exit.key) == false
        ? null
        : direction.scanDirection;
    return DirectBusPlan(
      direction.route,
      direction.toward,
      boarding,
      exit,
      direction.departures[boarding.key] ?? const [],
      scanDirection,
      direction.scanCode,
      meters,
      scheduledDeparture: scheduledDeparture,
      scheduledArrivalAtExit: scheduledArrivalAtExit,
      transferWalkDistanceM: transferWalkDistanceM,
      terminalsOnly: direction.terminalsOnly,
      travelBearingDeg: travelBearing,
      boardingCurbLocation: curb,
      nextStopName: next.name,
    );
  }

  _ScheduledDeparture? _nextScheduledDeparture(
    List<Duration> times,
    DateTime ready,
  ) {
    final options = _scheduledDepartures(times, ready, limit: 1);
    return options.isEmpty ? null : options.first;
  }

  List<_ScheduledDeparture> _scheduledDepartures(
    List<Duration> times,
    DateTime ready, {
    required int limit,
  }) {
    final firstDay = _serviceDayStart(ready);
    final options = <_ScheduledDeparture>[];
    for (
      var index = 0;
      index < times.length && options.length < limit;
      index++
    ) {
      final time = firstDay.add(times[index]);
      if (!time.isBefore(ready)) {
        options.add(_ScheduledDeparture(index, time));
      }
    }
    return options;
  }

  DateTime? _scheduledTimeAtStop(
    List<Duration>? times,
    _ScheduledDeparture boarding,
  ) {
    if (times == null || times.length <= boarding.index) return null;
    return _timeOnServiceDay(boarding.time, times[boarding.index]);
  }

  DateTime _timeOnServiceDay(DateTime departure, Duration stopTime) {
    final day = _serviceDayStart(departure);
    var time = day.add(stopTime);
    if (time.isBefore(departure)) time = time.add(const Duration(days: 1));
    return time;
  }

  void _sortItineraries(List<TransitItinerary> itineraries) {
    itineraries.sort((a, b) {
      final distanceDelta =
          a.firstLeg.boardingDistanceM - b.firstLeg.boardingDistanceM;
      // Prefer fewer transfers when boarding distances are similar.
      if (distanceDelta.abs() < 300) {
        final legs = a.legs.length.compareTo(b.legs.length);
        if (legs != 0) return legs;
      }
      if (distanceDelta != 0) {
        return distanceDelta < 0 ? -1 : 1;
      }
      return (a.firstLeg.scheduledDeparture ?? DateTime.utc(9999)).compareTo(
        b.firstLeg.scheduledDeparture ?? DateTime.utc(9999),
      );
    });
  }

  DirectBusPlan? plan(String destination, LatLng origin, {DateTime? now}) {
    final options = journeys(destination, origin, now: now);
    return options.isEmpty ? null : options.first.firstLeg;
  }
}

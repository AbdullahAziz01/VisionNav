import 'dart:async';

import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/direct_bus_planner.dart';
import 'package:visionnav_app/services/location_service.dart';
import 'package:visionnav_app/services/navigation/route_models.dart';
import 'package:visionnav_app/services/navigation/route_navigation_service.dart';
import 'package:visionnav_app/services/navigation/transit_gazetteer.dart';
import 'package:visionnav_app/services/voice_commands.dart';

typedef TripWalk = ({
  Place destination,
  DirectBusPlan? busPlan,
  TransitItinerary? itinerary,
});

class DestinationTripScreen extends StatefulWidget {
  const DestinationTripScreen({
    super.key,
    this.now = DateTime.now,
    this.locate,
    this.walkingRoute,
  });

  final DateTime Function() now;
  final Future<LatLng> Function()? locate;
  final Future<NavRoute> Function(LatLng origin, Place destination)?
  walkingRoute;

  @override
  State<DestinationTripScreen> createState() => _DestinationTripScreenState();
}

class _DestinationTripScreenState extends State<DestinationTripScreen> {
  final _voice = VoiceCommands.shared;
  final _destination = TextEditingController();
  bool _busy = false;
  String? _message;
  DirectBusPlanner? _planner;
  DirectBusPlan? _boardingPlan;
  TransitItinerary? _itinerary;
  bool _canRefreshWait = false;

  @override
  void initState() {
    super.initState();
    _voice.register(this, _handleVoice);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _voice.enabled) {
        unawaited(
          _voice.say('Where would you like to go? Say your destination.'),
        );
      }
    });
  }

  @override
  void dispose() {
    _voice.unregister(this);
    _destination.dispose();
    super.dispose();
  }

  Future<bool> _handleVoice(String words) async {
    if (!mounted || ModalRoute.of(context)?.isCurrent != true) return false;
    final command = normalizeCommand(words);
    if (command == 'screen commands') {
      await _voice.say('Say your destination, for example Karachi Company.');
      return true;
    }
    if (isGlobalVoiceCommand(command)) return false;
    if (command == 'yes' || command == 'no') {
      if (_boardingPlan == null) {
        await _voice.say(
          'There is no verified bus itinerary to confirm. Say your destination.',
        );
      } else if (command == 'yes') {
        _startBoardingWalk();
      } else {
        await _declineBoardingWalk();
      }
      return true;
    }
    if (command == 'walk to mapped stop' && _boardingPlan != null) {
      _startBoardingWalk();
      return true;
    }
    if (command == 'check wait' && _canRefreshWait) {
      await _plan(_destination.text);
      return true;
    }
    final destination = words.replaceFirst(
      RegExp(
        r'^(?:i want to go to|take me to|go to|destination)\s+',
        caseSensitive: false,
      ),
      '',
    );
    await _plan(destination);
    return true;
  }

  Future<void> _plan(String destination) async {
    if (_busy || destination.trim().isEmpty) return;
    FocusScope.of(context).unfocus();
    _destination.text = destination.trim();
    setState(() {
      _busy = true;
      _message = null;
      _boardingPlan = null;
      _itinerary = null;
      _canRefreshWait = false;
    });
    String message;
    DirectBusPlan? boardingPlan;
    TransitItinerary? itinerary;
    var canRefreshWait = false;
    try {
      final planner = _planner ??= await DirectBusPlanner.load();
      if (!mounted) return;
      if (!planner.serves(destination)) {
        message = planner.listsStop(destination)
            ? 'CDA lists $destination, but this app does not have a usable mapped route for that stop yet.'
            : 'I could not match $destination to a mapped stop on the ${planner.routeCount} supported CDA routes. Say a bus stop name, such as Karachi Company or Faizabad.';
      } else {
        final origin = await (widget.locate ?? _currentLocation)().timeout(
          const Duration(seconds: 15),
        );
        final now = widget.now();
        final options = planner.journeys(
          destination,
          origin,
          now: now,
          includeTransfers: true,
        );
        if (options.isEmpty) {
          message =
              'I cannot verify a complete bus itinerary to $destination. The mapped route directions and published schedules do not establish a service that reaches it now, or a timed transfer at a shared stop.';
        } else {
          final selection = await _selectItinerary(
            planner,
            options,
            origin,
            destination,
            now,
          );
          if (selection == null) {
            message =
                'I cannot verify a bus itinerary that is operating after the walk to any mapped boarding stop. Check the destination or try again during published service hours.';
          } else {
            itinerary = selection.itinerary;
            boardingPlan = itinerary.firstLeg;
            message = _itineraryOffer(
              itinerary,
              now,
              walkingDuration: selection.walkingDuration,
              routeDistanceVerified: selection.routeDistanceVerified,
              nearestStopVerified: selection.nearestStopVerified,
            );
            canRefreshWait = true;
          }
        }
      }
    } on LocationUnavailableException catch (error) {
      message = error.message;
    } on TimeoutException {
      message = 'Could not get your location. Check GPS and try again.';
    } on Exception catch (error) {
      message = 'Could not plan this trip: $error';
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _message = message;
      _boardingPlan = boardingPlan;
      _itinerary = itinerary;
      _canRefreshWait = canRefreshWait;
    });
    await _voice.say(message);
  }

  Future<LatLng> _currentLocation() async {
    final gps = await GeolocatorLocationService().getCurrentLocation();
    return LatLng(gps['latitude']!, gps['longitude']!);
  }

  /// Stops within this range need no walking-route API call.
  static const _alreadyAtStopM = 75.0;

  /// Do not consider a farther boarding stop when a nearer valid one exists
  /// within this margin (prevents Shaheen Chowk winning over G-10).
  static const _nearerStopSlackM = 750.0;

  Future<
    ({
      TransitItinerary itinerary,
      Duration? walkingDuration,
      bool routeDistanceVerified,
      bool nearestStopVerified,
    })?
  >
  _selectItinerary(
    DirectBusPlanner planner,
    List<TransitItinerary> options,
    LatLng origin,
    String destination,
    DateTime now,
  ) async {
    final boardingStops = <String, TransitStop>{};
    for (final option in options) {
      boardingStops[option.firstLeg.boarding.key] = option.firstLeg.boarding;
    }
    final orderedStops = boardingStops.values.toList()
      ..sort(
        (a, b) => const Distance()(
          origin,
          a.location,
        ).compareTo(const Distance()(origin, b.location)),
      );
    if (orderedStops.isEmpty) return null;

    final nearestStraightM = const Distance()(
      origin,
      orderedStops.first.location,
    );
    final maxCandidateStraightM = nearestStraightM + _nearerStopSlackM;

    final candidates =
        <
          ({
            TransitItinerary itinerary,
            double distanceM,
            Duration? duration,
            bool routeDistanceVerified,
            double straightLineM,
          })
        >[];
    var sawWalkingRouteFailure = false;
    var attemptedRoutes = 0;

    for (final stop in orderedStops) {
      final straightLineM = const Distance()(origin, stop.location);
      if (straightLineM > maxCandidateStraightM && candidates.isNotEmpty) {
        break;
      }
      if (attemptedRoutes >= 8) break;
      attemptedRoutes++;

      double accessM;
      Duration? walkDuration;
      var routeVerified = false;

      if (straightLineM <= _alreadyAtStopM) {
        accessM = straightLineM;
        walkDuration = Duration.zero;
        routeVerified = true;
      } else {
        try {
          final route = await _walkingRoute(
            origin,
            Place(name: stop.name, location: stop.location),
          ).timeout(const Duration(seconds: 10));
          if (!route.distanceM.isFinite ||
              route.distanceM < 0 ||
              route.distanceM + 25 < straightLineM ||
              !route.durationS.isFinite ||
              route.durationS < 0) {
            sawWalkingRouteFailure = true;
            // Keep the nearer mapped stop with a straight-line estimate instead
            // of discarding it for a far stop whose ORS call happened to work.
            accessM = straightLineM;
            walkDuration = null;
            routeVerified = false;
          } else {
            accessM = route.distanceM;
            walkDuration = Duration(seconds: route.durationS.ceil());
            routeVerified = true;
          }
        } on Exception {
          sawWalkingRouteFailure = true;
          accessM = straightLineM;
          walkDuration = null;
          routeVerified = false;
        }
      }

      final timed = planner.journeys(
        destination,
        origin,
        now: now,
        initialWalkDuration: walkDuration ?? Duration.zero,
        initialBoardingKey: stop.key,
        includeTransfers: true,
      );
      if (timed.isEmpty) continue;

      candidates.add((
        itinerary: timed.first.withFirstLeg(
          timed.first.firstLeg.withAccessDistance(
            distanceM: accessM,
            isWalkingRoute: routeVerified,
          ),
        ),
        distanceM: accessM,
        duration: walkDuration,
        routeDistanceVerified: routeVerified,
        straightLineM: straightLineM,
      ));
    }

    if (candidates.isEmpty) return null;

    candidates.sort((a, b) {
      final byStraight = a.straightLineM.compareTo(b.straightLineM);
      if (byStraight != 0) return byStraight;
      final byLegs = a.itinerary.legs.length.compareTo(b.itinerary.legs.length);
      if (byLegs != 0) return byLegs;
      final byAccess = a.distanceM.compareTo(b.distanceM);
      if (byAccess != 0) return byAccess;
      return (a.itinerary.firstLeg.scheduledDeparture ?? DateTime.utc(9999))
          .compareTo(
            b.itinerary.firstLeg.scheduledDeparture ?? DateTime.utc(9999),
          );
    });

    final best = candidates.first;
    final nearerExistsUnrouted = candidates.any(
      (c) =>
          c.straightLineM + 25 < best.straightLineM &&
          !c.routeDistanceVerified,
    );
    return (
      itinerary: best.itinerary,
      walkingDuration: best.duration,
      routeDistanceVerified: best.routeDistanceVerified,
      nearestStopVerified: !sawWalkingRouteFailure && !nearerExistsUnrouted,
    );
  }

  Future<NavRoute> _walkingRoute(LatLng origin, Place destination) {
    final route = widget.walkingRoute;
    if (route != null) return route(origin, destination);
    return RouteNavigationService.instance.router.walkingRoute(
      origin,
      destination,
    );
  }

  String _itineraryOffer(
    TransitItinerary itinerary,
    DateTime now, {
    required Duration? walkingDuration,
    required bool routeDistanceVerified,
    required bool nearestStopVerified,
  }) {
    final first = itinerary.firstLeg;
    final access = first.boardingDistanceM;
    final beyondGuideline = access > DirectBusPlan.maximumBoardingWalkM;
    final distanceText = access >= 1000
        ? '${(access / 1000).toStringAsFixed(access >= 10000 ? 0 : 1)} kilometres'
        : '${access.round()} metres';
    final distanceMessage = routeDistanceVerified
        ? beyondGuideline
              ? 'The walking route to the boarding stop is $distanceText, beyond the 2 kilometre guideline.'
              : 'The walking route to the boarding stop is $distanceText, within the 2 kilometre guideline.'
        : beyondGuideline
        ? 'The straight-line estimate to the boarding stop is about $distanceText, already beyond 2 kilometres; the actual walk will be longer.'
        : 'The straight-line estimate to the boarding stop is about $distanceText; walking-route verification was unavailable.';
    final departure = first.scheduledDeparture;
    final scheduleCaveat = departure != null && walkingDuration == null
        ? 'Walking time is unavailable, so I cannot verify whether that departure can be reached after the walk. '
        : '';
    final legDepartures = [
      for (var i = 1; i < itinerary.legs.length; i++)
        if (itinerary.legs[i].scheduledDeparture case final time?)
          'Then switch to ${itinerary.legs[i].route} toward ${itinerary.legs[i].toward} at ${itinerary.legs[i].boarding.name}; scheduled departure ${_formatLocalTime(time)}.',
    ].join(' ');
    final nearestMessage = nearestStopVerified
        ? 'This is the nearest mapped boarding stop that reaches your destination on a published route. '
        : 'I could not fully verify walking routes for every nearer candidate, but this is the closest mapped boarding stop that still reaches your destination. ';
    final transferMessage = itinerary.hasTransfers
        ? 'There is no single direct bus from your location to the destination on the mapped routes, so this plan uses a transfer. Transfer connections use published stop times; actual delays may make them unavailable. '
        : '';
    final waitMessage = first.scheduledWaitSpeech(
      now,
      timeToBoard: walkingDuration ?? Duration.zero,
    );
    final farWalkAsk = beyondGuideline
        ? 'The boarding stop is more than 2 kilometres away. Say yes only if you want to continue walking there anyway. '
        : '';
    final transferLegs = itinerary.hasTransfers
        ? ' ${itinerary.summary}'
        : '';
    final terminalsMessage = first.terminalsOnly
        ? 'Only the published start and end terminals are mapped for this route; intermediate stops are not guided. '
        : '';
    return 'To reach your destination, take ${first.route} toward ${first.toward}. '
        'Board at ${first.boarding.name}. Get off at ${first.exit.name}. '
        '$terminalsMessage'
        '${first.roadSideGuidanceSpeech} '
        '$transferLegs $nearestMessage $distanceMessage $scheduleCaveat$legDepartures $waitMessage '
        'Live bus GPS arrivals are unavailable to this app. Confirm service is running today. '
        'Never step into the road to scan. '
        '$transferMessage$farWalkAsk'
        'Navigation will guide you to the estimated boarding kerb at ${first.boarding.name}, not to ${first.exit.name}. '
        'Would you like walking directions to ${first.boarding.name} for ${first.route} toward ${first.toward}? Say yes or no.';
  }

  String _formatLocalTime(DateTime time) {
    final clock = time.toUtc().add(const Duration(hours: 5));
    final hour = clock.hour % 12 == 0 ? 12 : clock.hour % 12;
    final minute = clock.minute.toString().padLeft(2, '0');
    final period = clock.hour < 12 ? 'AM' : 'PM';
    return '$hour:$minute $period Islamabad time';
  }

  void _startBoardingWalk() {
    final plan = _boardingPlan;
    if (_busy || plan == null) return;
    Navigator.of(context).pop<TripWalk>((
      destination: Place(
        name: plan.boarding.name,
        location: plan.boardingWalkLocation,
        displayName: plan.boardingCurbLocation == null
            ? null
            : 'Estimated boarding kerb for ${plan.route} toward ${plan.toward}',
      ),
      busPlan: plan,
      itinerary: _itinerary,
    ));
  }

  Future<void> _declineBoardingWalk() async {
    setState(() {
      _boardingPlan = null;
      _itinerary = null;
      _canRefreshWait = false;
      _message = 'Trip cancelled. You will not be guided to the stop.';
    });
    await _voice.say('Trip cancelled. You will not be guided to the stop.');
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Plan a bus trip'),
      actions: [
        IconButton(
          tooltip: 'Resume voice commands',
          icon: const Icon(Icons.mic),
          onPressed: () => _voice.start(),
        ),
      ],
    ),
    body: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Text(
          'Where would you like to go?',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 12),
        const Text(
          'Say or type a bus stop name, such as Karachi Company or Faizabad.',
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _destination,
          enabled: !_busy,
          decoration: const InputDecoration(labelText: 'Destination'),
          textInputAction: TextInputAction.search,
          onSubmitted: _plan,
          onChanged: (_) {
            if (_message == null) return;
            setState(() {
              _message = null;
              _boardingPlan = null;
              _itinerary = null;
              _canRefreshWait = false;
            });
          },
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _busy ? null : () => _plan(_destination.text),
          child: Text(_busy ? 'Finding your trip' : 'Find a bus trip'),
        ),
        if (_message case final message?) ...[
          const SizedBox(height: 16),
          Semantics(liveRegion: true, child: Text(message)),
        ],
        if (_canRefreshWait && !_busy) ...[
          if (_boardingPlan != null) ...[
            FilledButton(
              onPressed: _startBoardingWalk,
              child: const Text('Yes, walk to mapped stop'),
            ),
            TextButton(
              onPressed: _declineBoardingWalk,
              child: const Text('No, cancel trip'),
            ),
          ],
          TextButton(
            onPressed: () => _plan(_destination.text),
            child: const Text('Check scheduled wait again'),
          ),
        ],
      ],
    ),
  );
}

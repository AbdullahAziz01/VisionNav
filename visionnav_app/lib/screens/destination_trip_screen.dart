import 'dart:async';

import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/direct_bus_planner.dart';
import 'package:visionnav_app/services/location_service.dart';
import 'package:visionnav_app/services/navigation/route_models.dart';
import 'package:visionnav_app/services/navigation/route_navigation_service.dart';
import 'package:visionnav_app/services/voice_commands.dart';

typedef TripWalk = ({Place destination, DirectBusPlan? busPlan});

class DestinationTripScreen extends StatefulWidget {
  const DestinationTripScreen({
    super.key,
    this.now = DateTime.now,
    this.locate,
  });

  final DateTime Function() now;
  final Future<LatLng> Function()? locate;

  @override
  State<DestinationTripScreen> createState() => _DestinationTripScreenState();
}

class _DestinationTripScreenState extends State<DestinationTripScreen> {
  final _voice = VoiceCommands.shared;
  final _destination = TextEditingController();
  bool _busy = false;
  String? _message;
  DirectBusPlanner? _planner;
  Place? _walkTo;
  DirectBusPlan? _boardingPlan;
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
      if (_walkTo == null) {
        await _voice.say(
          'There is no walking offer to answer. Say your destination.',
        );
      } else {
        await _answerWalking(command == 'yes');
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
      _walkTo = null;
      _boardingPlan = null;
      _canRefreshWait = false;
    });
    String message;
    Place? walkTo;
    DirectBusPlan? boardingPlan;
    var canRefreshWait = false;
    try {
      final planner = _planner ??= await DirectBusPlanner.load();
      if (!mounted) return;
      if (!planner.serves(destination)) {
        message =
            'No supported direct route for $destination. '
            'Try ${planner.destinations.join(', ')}.';
      } else {
        final origin = await (widget.locate ?? _currentLocation)().timeout(
          const Duration(seconds: 15),
        );
        final plan = planner.plan(destination, origin);
        if (plan == null) {
          message =
              'No suitable boarding stop near your current location for $destination.';
        } else {
          final status = await _checkSchedule(plan, origin);
          message = status.message;
          walkTo = status.walkTo;
          if (walkTo == null) boardingPlan = plan;
          canRefreshWait = true;
        }
      }
    } on LocationUnavailableException catch (error) {
      message = error.message;
    } on TimeoutException {
      message = 'Could not get your location. Check GPS and try again.';
    } catch (_) {
      message = 'Could not plan this trip. Please try again.';
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _message = message;
      _walkTo = walkTo;
      _boardingPlan = boardingPlan;
      _canRefreshWait = canRefreshWait;
    });
    await _voice.say(message);
  }

  Future<LatLng> _currentLocation() async {
    final gps = await GeolocatorLocationService().getCurrentLocation();
    return LatLng(gps['latitude']!, gps['longitude']!);
  }

  Future<({String message, Place? walkTo})> _checkSchedule(
    DirectBusPlan plan,
    LatLng origin,
  ) async {
    if (plan.departures.isEmpty) {
      return (
        message:
            '${plan.summary} No published departure estimate is available.',
        walkTo: null,
      );
    }
    final atMappedStop = const Distance()(origin, plan.boarding.location) <= 25;
    Duration? timeToBoard;
    if (atMappedStop) {
      timeToBoard = Duration.zero;
    } else if (plan.nextDeparture(widget.now()) != null) {
      try {
        final route = await RouteNavigationService.instance.router.walkingRoute(
          origin,
          Place(name: plan.boarding.name, location: plan.boarding.location),
        );
        if (route.durationS > 0 && route.durationS.isFinite) {
          timeToBoard = Duration(seconds: route.durationS.ceil(), minutes: 2);
        }
      } catch (_) {
        // The published timetable is still useful without a walking estimate.
      }
    }
    final now = widget.now();
    final departure = plan.nextDeparture(
      now,
      timeToBoard: timeToBoard ?? Duration.zero,
    );
    if (departure == null) {
      final reason = plan.nextDeparture(now) == null
          ? 'No more departures are listed today for this stop and direction.'
          : 'The last listed bus leaves before your estimated boarding time.';
      return (
        message:
            '$reason Would you like walking directions to ${plan.exit.name}? Say yes or no.',
        walkTo: Place(name: plan.exit.name, location: plan.exit.location),
      );
    }
    final clock = departure.add(const Duration(hours: 5));
    final hour = clock.hour % 12 == 0 ? 12 : clock.hour % 12;
    final minute = clock.minute.toString().padLeft(2, '0');
    final period = clock.hour < 12 ? 'AM' : 'PM';
    final minutes =
        (departure.difference(now.add(timeToBoard ?? Duration.zero)).inSeconds /
                60)
            .ceil();
    final wait = timeToBoard == null
        ? 'Walking time is unavailable, so I cannot tell if you can catch it.'
        : atMappedStop
        ? 'If you are at the boarding point, the scheduled wait is about $minutes minutes.'
        : 'The scheduled wait after your estimated walk is about $minutes minutes.';
    return (
      message:
          '${plan.summary} A departure is listed for $hour:$minute $period Islamabad time. $wait The map pin is approximate. Confirm the boarding point and service. To walk to the mapped stop, say walk to mapped stop.',
      walkTo: null,
    );
  }

  Future<void> _answerWalking(bool accepted) async {
    final destination = _walkTo;
    if (_busy || destination == null) return;
    setState(() {
      _busy = true;
      _walkTo = null;
    });
    if (!accepted) await _voice.say('Trip cancelled.');
    if (!mounted || ModalRoute.of(context)?.isCurrent != true) return;
    Navigator.of(context).pop<TripWalk>(
      accepted ? (destination: destination, busPlan: null) : null,
    );
  }

  void _startBoardingWalk() {
    final plan = _boardingPlan;
    if (_busy || plan == null) return;
    Navigator.of(context).pop<TripWalk>((
      destination: Place(
        name: plan.boarding.name,
        location: plan.boarding.location,
      ),
      busPlan: plan,
    ));
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
        const Text('Say or type a destination. Try Karachi Company on FR-07.'),
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
              _walkTo = null;
              _boardingPlan = null;
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
        if (_walkTo != null) ...[
          FilledButton(
            onPressed: () => _answerWalking(true),
            child: const Text('Yes, walk'),
          ),
          TextButton(
            onPressed: () => _answerWalking(false),
            child: const Text('No, cancel trip'),
          ),
        ] else if (_canRefreshWait && !_busy) ...[
          if (_boardingPlan != null)
            FilledButton(
              onPressed: _startBoardingWalk,
              child: const Text('Walk to mapped stop'),
            ),
          TextButton(
            onPressed: () => _plan(_destination.text),
            child: const Text('Check scheduled wait again'),
          ),
        ],
      ],
    ),
  );
}

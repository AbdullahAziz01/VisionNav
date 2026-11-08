import 'dart:async';

import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/direct_bus_planner.dart';
import 'package:visionnav_app/services/location_service.dart';
import 'package:visionnav_app/services/voice_commands.dart';

class DestinationTripScreen extends StatefulWidget {
  const DestinationTripScreen({super.key});

  @override
  State<DestinationTripScreen> createState() => _DestinationTripScreenState();
}

class _DestinationTripScreenState extends State<DestinationTripScreen> {
  final _voice = VoiceCommands.shared;
  final _destination = TextEditingController();
  bool _busy = false;
  String? _message;
  DirectBusPlanner? _planner;

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
    });
    String message;
    try {
      final planner = _planner ??= await DirectBusPlanner.load();
      if (!mounted) return;
      if (!planner.serves(destination)) {
        message =
            'No supported direct route for $destination. '
            'Try ${planner.destinations.join(', ')}.';
      } else {
        final gps = await GeolocatorLocationService()
            .getCurrentLocation()
            .timeout(const Duration(seconds: 15));
        final plan = planner.plan(
          destination,
          LatLng(gps['latitude']!, gps['longitude']!),
        );
        message = plan == null
            ? 'No suitable boarding stop near your current location for $destination.'
            : '${plan.summary} Check the boarding point and service before leaving.';
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
    });
    await _voice.say(message);
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
      ],
    ),
  );
}

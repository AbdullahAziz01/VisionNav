import 'dart:async';
import 'package:visionnav_app/services/voice_commands.dart';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:visionnav_app/services/bus_trip.dart';

class BusTripScreen extends StatefulWidget {
  const BusTripScreen({super.key});

  @override
  State<BusTripScreen> createState() => _BusTripScreenState();
}

class _BusTripScreenState extends State<BusTripScreen> {
  late Future<List<BusTrip>> _options = _loadOptions();
  String? _line;
  BusTrip? _selected;
  final _voice = VoiceCommands.shared;
  int _routePage = 0;

  @override
  void initState() {
    super.initState();
    _voice.register(this, _handleVoice);
  }

  @override
  void dispose() {
    _voice.unregister(this);
    super.dispose();
  }

  Future<void> _readRoutes(List<String> lines) async {
    final page = lines.skip(_routePage * 5).take(5).toList();
    await _voice.say(
      page
          .asMap()
          .entries
          .map((e) => '${e.key + 1}. ${e.value}')
          .followedBy([
            'Say select route and its name or number. Say next routes for more.',
          ])
          .join('. '),
    );
  }

  Future<void> _readDirections(List<BusTrip> options) async {
    final directions = options.where((t) => t.line == _line).toList();
    if (directions.isEmpty) {
      await _voice.say('Choose a route first. Say list routes.');
      return;
    }
    await _voice.say(
      directions
          .asMap()
          .entries
          .map((e) => '${e.key + 1}. Toward ${e.value.destination}')
          .followedBy(['Say select direction and its number.'])
          .join('. '),
    );
  }

  Future<bool> _handleVoice(String words) async {
    if (!mounted || ModalRoute.of(context)?.isCurrent != true) return false;
    final c = normalizeCommand(words);
    final options = await _options;
    if (!mounted) return true;
    final lines = options.map((t) => t.line).toSet().toList();
    if (c == 'list routes' || c == 'read routes') {
      _routePage = 0;
      await _readRoutes(lines);
    } else if (c == 'next routes' || c == 'previous routes') {
      final pages = (lines.length / 5).ceil();
      _routePage = c == 'next routes'
          ? (_routePage + 1) % pages
          : (_routePage - 1 + pages) % pages;
      await _readRoutes(lines);
    } else if (c.startsWith('select route ')) {
      final value = c.substring('select route '.length);
      final number = spokenNumber(value);
      String? chosen;
      if (number != null) {
        final index = _routePage * 5 + number - 1;
        if (number >= 1 && number <= 5 && index < lines.length) {
          chosen = lines[index];
        }
      } else {
        final matches = lines
            .where((line) => routeVoiceKey(line) == routeVoiceKey(value))
            .toList();
        if (matches.length == 1) chosen = matches.single;
      }
      if (chosen == null) {
        await _voice.say('Route not found. Say list routes.');
      } else {
        setState(() {
          _line = chosen;
          _selected = null;
        });
        await _voice.say('Selected $chosen.');
        await _readDirections(options);
      }
    } else if (c == 'list directions' || c == 'read directions') {
      await _readDirections(options);
    } else if (c.startsWith('select direction ')) {
      final value = c.substring('select direction '.length);
      final directions = options.where((t) => t.line == _line).toList();
      final number = spokenNumber(value);
      BusTrip? choice;
      if (number != null && number > 0 && number <= directions.length) {
        choice = directions[number - 1];
      } else {
        final matches = directions
            .where((t) => normalizeCommand(t.destination) == value)
            .toList();
        if (matches.length == 1) choice = matches.single;
      }
      if (choice == null) {
        await _voice.say('Direction not found. Say list directions.');
      } else {
        setState(() => _selected = choice);
        await _voice.say(
          'Selected ${choice.label}. Say continue for walking directions.',
        );
      }
    } else if (c == 'continue' || c == 'continue to walking directions') {
      if (_selected == null) {
        await _voice.say('Choose a route and direction first.');
      } else {
        Navigator.of(context).pop(_selected);
      }
    } else if (c == 'screen commands') {
      await _voice.say(
        'Say list routes, next routes, previous routes, select route and its name or number, list directions, select direction and its number, continue, or cancel.',
      );
    } else {
      return false;
    }
    return true;
  }

  Future<List<BusTrip>> _loadOptions() async {
    final raw = await rootBundle.loadString('assets/bus_trip_options.json');
    return (jsonDecode(raw) as List<dynamic>)
        .map((entry) => BusTrip.fromJson(entry as Map<String, dynamic>))
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
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
      body: FutureBuilder<List<BusTrip>>(
        future: _options,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return Center(
              child: FilledButton(
                onPressed: () => setState(() => _options = _loadOptions()),
                child: const Text('Could not load bus routes. Retry'),
              ),
            );
          }
          final options = snapshot.data;
          if (options == null) {
            return const Center(
              child: CircularProgressIndicator(
                semanticsLabel: 'Loading bus routes',
              ),
            );
          }
          return ListView(
            padding: const EdgeInsets.all(24),
            children: [
              const Text(
                'Choose your bus route and the destination shown on its sign. '
                'Then say the name of the bus stand you want to walk to.',
              ),
              const SizedBox(height: 20),
              DropdownButtonFormField<String>(
                key: ValueKey('route-$_line'),
                initialValue: _line,
                decoration: const InputDecoration(labelText: 'Bus route'),
                isExpanded: true,
                items: [
                  for (final line in options.map((trip) => trip.line).toSet())
                    DropdownMenuItem(value: line, child: Text(line)),
                ],
                onChanged: (line) => setState(() {
                  _line = line;
                  _selected = null;
                }),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<BusTrip>(
                key: ValueKey('direction-${_selected?.label}-$_line'),
                initialValue: _selected,
                decoration: const InputDecoration(labelText: 'Bus direction'),
                isExpanded: true,
                items: [
                  for (final trip in options.where(
                    (trip) => trip.line == _line,
                  ))
                    DropdownMenuItem(
                      value: trip,
                      child: Text('Toward ${trip.destination}'),
                    ),
                ],
                onChanged: _line == null
                    ? null
                    : (trip) => setState(() => _selected = trip),
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _selected == null
                    ? null
                    : () => Navigator.of(context).pop(_selected),
                icon: const Icon(Icons.directions_walk),
                label: const Text('Continue to walking directions'),
              ),
            ],
          );
        },
      ),
    );
  }
}

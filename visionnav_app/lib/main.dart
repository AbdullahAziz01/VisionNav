import 'package:visionnav_app/services/direct_bus_planner.dart';
import 'dart:async';
import 'package:visionnav_app/services/voice_commands.dart';
import 'package:flutter/material.dart';
import 'package:visionnav_app/core/theme.dart';
import 'package:visionnav_app/screens/bus_trip_screen.dart';
import 'package:visionnav_app/screens/destination_trip_screen.dart';
import 'package:visionnav_app/screens/home_screen.dart';
import 'package:visionnav_app/screens/camera_screen.dart';
import 'package:visionnav_app/screens/navigation_screen.dart';
import 'package:visionnav_app/screens/settings_screen.dart';
import 'package:visionnav_app/screens/help_screen.dart';
import 'package:visionnav_app/services/bus_trip.dart';
import 'package:visionnav_app/services/navigation/route_navigation_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const VisionNavApp());
}

class VisionNavApp extends StatelessWidget {
  const VisionNavApp({
    super.key,
    this.enableVoice = true,
    this.startWithCamera = true,
  });
  final bool enableVoice;
  final bool startWithCamera;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VisionNav',
      theme: AppTheme.darkTheme,
      home: MainLayout(
        enableVoice: enableVoice,
        startWithCamera: startWithCamera,
      ),
      debugShowCheckedModeBanner: false,
    );
  }
}

class MainLayout extends StatefulWidget {
  const MainLayout({
    super.key,
    this.enableVoice = true,
    this.startWithCamera = true,
  });
  final bool enableVoice;
  final bool startWithCamera;

  @override
  State<MainLayout> createState() => _MainLayoutState();
}

class _MainLayoutState extends State<MainLayout> {
  late int _currentIndex;
  final _voice = VoiceCommands.shared;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.startWithCamera ? 1 : 0;
    _voice.register(this, _handleVoice);
    if (widget.enableVoice) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) unawaited(_voice.start());
      });
    }
  }

  Future<bool> _handleVoice(String words) async {
    final command = normalizeCommand(words);
    final destinations = {
      'open home': 0,
      'home': 0,
      'go home': 0,
      'open vision': 1,
      'open camera': 1,
      'camera': 1,
      'scan bus': 1,
      'open visionnav': 1,
      'open vision nav': 1,
      'add location': 2,
      'open gps': 2,
      'open navigation': 2,
      'navigation': 2,
      'open settings': 3,
      'settings': 3,
      'open help': 4,
      'help': 4,
    };
    if (destinations.containsKey(command)) {
      final index = destinations[command]!;
      await _voice.say(
        [
          'Opening home.',
          'Opening camera.',
          'Opening navigation.',
          'Opening settings.',
          'Opening help.',
        ][index],
      );
      if (!mounted) return true;
      Navigator.of(context).popUntil((route) => route.isFirst);
      setState(() => _currentIndex = index);
      return true;
    }
    if (command == 'plan a bus trip' || command == 'plan bus trip') {
      if (mounted) unawaited(_planBusTrip());
      return true;
    }
    if (command == 'go back' || command == 'back' || command == 'cancel') {
      if (Navigator.of(context).canPop()) {
        Navigator.of(context).pop();
      } else {
        setState(() => _currentIndex = 0);
      }
      await _voice.say('Going back.');
      return true;
    }
    if (command == 'end bus trip') {
      _endBusTrip();
      await _voice.say('Bus trip ended.');
      return true;
    }
    if (command == 'screen commands' && _currentIndex == 0) {
      await _voice.say(
        'Say plan a bus trip, open camera, add location, open settings, or open help.',
      );
      return true;
    }
    if ((command == 'read help' || command == 'screen commands') &&
        _currentIndex == 4) {
      await _voice.say(
        'Say plan a bus trip, then say your destination. The planner proposes a boarding stop, bus direction, and exit stop. Confirm the boarding point and service before leaving. Say voice help for more commands.',
      );
      return true;
    }
    if (command == 'voice help' || command == 'what can i say') {
      await _voice.say(
        'Say open home, open camera, add location, plan a bus trip, open settings, open help, go back, or stop listening. Say screen commands for controls on this screen.',
      );
      return true;
    }
    return false;
  }

  bool _planningTrip = false;
  BusTrip? _busTrip;
  RouteNavigationService? _tripNavigation;
  bool _walkingToBoard = false;
  DirectBusPlan? _activeBusPlan;

  Future<void> _planBusTrip() async {
    if (_planningTrip) return;
    _planningTrip = true;
    if (_currentIndex != 0) setState(() => _currentIndex = 0);
    try {
      final walkTo = await Navigator.of(context).push<TripWalk>(
        MaterialPageRoute(builder: (_) => const DestinationTripScreen()),
      );
      if (!mounted || walkTo == null) return;
      final navigation = RouteNavigationService.instance;
      _tripNavigation?.snapshot.removeListener(_onTripNavigationChanged);
      _tripNavigation = null;
      await navigation.stopNavigation(clearDestination: true);
      if (!mounted) return;
      final busPlan = walkTo.busPlan;
      if (busPlan != null) {
        _tripNavigation = navigation;
        navigation.snapshot.addListener(_onTripNavigationChanged);
      }
      final walking = navigation.startWalkingTo(
        walkTo.destination,
        shortest: busPlan == null,
      );
      setState(() {
        _busTrip = busPlan?.scannerTrip;
        _activeBusPlan = busPlan;
        _walkingToBoard = busPlan != null;
        _currentIndex = busPlan == null ? 2 : 1;
      });
      try {
        await walking;
      } catch (_) {
        // Navigation already reports routing errors in its snapshot and speech.
      }
    } finally {
      _planningTrip = false;
    }
  }

  Future<void> _planManualBusTrip() async {
    if (_planningTrip) return;
    _planningTrip = true;
    if (_currentIndex == 1) setState(() => _currentIndex = 0);
    final trip = await Navigator.of(
      context,
    ).push<BusTrip>(MaterialPageRoute(builder: (_) => const BusTripScreen()));
    _planningTrip = false;
    if (!mounted || trip == null) return;

    final navigation = RouteNavigationService.instance;
    _tripNavigation?.snapshot.removeListener(_onTripNavigationChanged);
    await navigation.stopNavigation(clearDestination: true);
    if (!mounted) return;

    _tripNavigation = navigation;
    navigation.snapshot.addListener(_onTripNavigationChanged);
    setState(() {
      _busTrip = trip;
      _activeBusPlan = null;
      _walkingToBoard = false;
      _currentIndex = 2;
    });
  }

  void _onTripNavigationChanged() {
    final state = _tripNavigation?.current.state;
    if (state == NavState.arrived) {
      final plan = _activeBusPlan;
      final reachedBoardingTarget =
          plan == null ||
          _tripNavigation?.current.place?.location == plan.boarding.location;
      final announceArrival =
          _walkingToBoard &&
          reachedBoardingTarget &&
          (_currentIndex == 1 || _currentIndex == 2) &&
          WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed;
      _tripNavigation?.snapshot.removeListener(_onTripNavigationChanged);
      setState(() {
        _walkingToBoard = false;
        if (!reachedBoardingTarget) {
          _busTrip = null;
          _activeBusPlan = null;
          _tripNavigation = null;
        } else if (_currentIndex == 1 || _currentIndex == 2) {
          _currentIndex = 1;
        }
      });
      if (announceArrival) {
        unawaited(
          _voice.say(
            'Near the mapped stop. Confirm the boarding point. ${_scheduledWait()}',
          ),
        );
      }
    }
  }

  String _scheduledWait() {
    final now = DateTime.now();
    final next = _activeBusPlan?.nextDeparture(now);
    if (next == null) return 'No more departures are listed today.';
    final minutes = (next.difference(now).inSeconds / 60).ceil();
    return 'The scheduled wait is about $minutes minutes.';
  }

  void _openVision() => setState(() => _currentIndex = 1);

  void _endBusTrip() {
    _tripNavigation?.snapshot.removeListener(_onTripNavigationChanged);
    final navigation = _tripNavigation;
    _tripNavigation = null;
    setState(() {
      _busTrip = null;
      _activeBusPlan = null;
      _walkingToBoard = false;
    });
    navigation?.stopNavigation(clearDestination: true);
  }

  @override
  void dispose() {
    _tripNavigation?.snapshot.removeListener(_onTripNavigationChanged);
    _voice.unregister(this);
    unawaited(_voice.stop());
    super.dispose();
  }

  Widget _screenForIndex(int index) {
    switch (index) {
      case 0:
        return HomeScreen(
          onPlanBusTrip: _planBusTrip,
          onManualTrip: _planManualBusTrip,
        );
      case 1:
        return CameraScreen(
          busTrip: _walkingToBoard ? null : _busTrip,
          walkingNavigation: _walkingToBoard ? _tripNavigation : null,
          scheduledWait: !_walkingToBoard && _activeBusPlan != null
              ? _scheduledWait
              : null,
          onEndBusTrip: _endBusTrip,
        );
      case 2:
        return NavigationScreen(busTrip: _busTrip, onScanBus: _openVision);
      case 3:
        return const SettingsScreen();
      case 4:
        return const HelpScreen();
      default:
        return const HomeScreen();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          Expanded(child: _screenForIndex(_currentIndex)),
          if (widget.enableVoice)
            AnimatedBuilder(
              animation: _voice,
              builder: (context, _) => SafeArea(
                top: false,
                bottom: false,
                child: ListTile(
                  dense: true,
                  leading: const Icon(Icons.mic),
                  title: Text(_voice.status),
                  trailing: TextButton(
                    onPressed: () =>
                        _voice.enabled ? _voice.stop() : _voice.start(),
                    child: Text(
                      _voice.enabled ? 'Pause voice' : 'Resume voice',
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        type: BottomNavigationBarType.fixed,
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Home'),
          BottomNavigationBarItem(
            icon: Icon(Icons.camera_alt),
            label: 'Vision',
          ),
          BottomNavigationBarItem(icon: Icon(Icons.navigation), label: 'Nav'),
          BottomNavigationBarItem(
            icon: Icon(Icons.settings),
            label: 'Settings',
          ),
          BottomNavigationBarItem(icon: Icon(Icons.help), label: 'Help'),
        ],
      ),
    );
  }
}

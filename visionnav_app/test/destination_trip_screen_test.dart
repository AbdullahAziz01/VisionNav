import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/screens/destination_trip_screen.dart';
import 'package:visionnav_app/services/navigation/route_models.dart';
import 'package:visionnav_app/services/voice_commands.dart';

void main() {
  // ~180 m from G-10 Markaz so walking-route verification is exercised
  // (at the stop pin itself the planner treats the user as already there).
  const origin = LatLng(33.6752, 73.0132);
  final now = DateTime.utc(2026, 11, 8, 7);

  for (final scenario in [
    (
      distanceM: 1999,
      phrase: 'within the 2 kilometre guideline',
      distancePhrase: '2.0 kilometres',
    ),
    (
      distanceM: 2500,
      phrase: 'beyond the 2 kilometre guideline',
      distancePhrase: '2.5 kilometres',
    ),
  ]) {
    testWidgets(
      'states the walking distance and asks before guidance at ${scenario.distanceM}m',
      (tester) async {
        TripWalk? result;
        await _openPlanner(
          tester,
          origin: origin,
          now: now,
          boardingDistanceM: scenario.distanceM.toDouble(),
          onResult: (value) => result = value,
        );

        expect(
          find.textContaining(scenario.phrase),
          findsOneWidget,
          reason: tester
              .widgetList<Text>(find.byType(Text))
              .map((text) => text.data)
              .join(' | '),
        );
        expect(
          find.textContaining(scenario.distancePhrase),
          findsOneWidget,
        );
        expect(
          find.textContaining('Live bus GPS arrivals are unavailable'),
          findsOneWidget,
        );
        expect(
          find.textContaining('CDA schedule estimate, not a live bus arrival'),
          findsOneWidget,
        );
        expect(
          find.textContaining('wait on the left-hand kerb'),
          findsOneWidget,
        );
        await tester.drag(find.byType(ListView), const Offset(0, -900));
        await tester.pumpAndSettle();
        expect(find.text('Yes, walk to mapped stop'), findsOneWidget);
        expect(result, isNull);

        await tester.runAsync(() => VoiceCommands.shared.dispatch('yes'));
        await tester.pumpAndSettle();

        expect(result?.destination.name, 'G-10 Markaz');
        expect(result?.busPlan?.route, 'FR-07');
        expect(result?.itinerary?.firstLeg.toward, 'PIMS Hospital');
      },
    );
  }

  testWidgets('no cancels the offered trip without starting guidance', (
    tester,
  ) async {
    TripWalk? result;
    await _openPlanner(
      tester,
      origin: origin,
      now: now,
      boardingDistanceM: 900,
      onResult: (value) => result = value,
    );

    await tester.drag(find.byType(ListView), const Offset(0, -900));
    await tester.pumpAndSettle();
    expect(find.text('Yes, walk to mapped stop'), findsOneWidget);
    await tester.runAsync(() => VoiceCommands.shared.dispatch('no'));
    await tester.pumpAndSettle();

    expect(result, isNull);
    expect(find.textContaining('Trip cancelled'), findsOneWidget);
  });

  testWidgets(
    'labels straight-line distance when walking routing is unavailable',
    (tester) async {
      await _openPlanner(
        tester,
        origin: origin,
        now: now,
        boardingDistanceM: 900,
        walkingRouteUnavailable: true,
        onResult: (_) {},
      );

      expect(find.textContaining('straight-line estimate'), findsOneWidget);
      expect(
        find.textContaining('walking-route verification was unavailable'),
        findsOneWidget,
      );
      expect(find.textContaining('closest mapped boarding stop'), findsOneWidget);
      expect(
        find.textContaining('estimated boarding kerb at G-10 Markaz, not to'),
        findsOneWidget,
      );
      expect(find.textContaining('walking route to the boarding stop is'), findsNothing);
    },
  );

  testWidgets(
    'keeps nearest boarding stop when only a far stop has a walking route',
    (tester) async {
      // Slightly away from G-10 so ORS is attempted, then forced to fail.
      const nearG10 = LatLng(33.6780, 73.0160);
      TripWalk? result;
      await _openPlanner(
        tester,
        origin: nearG10,
        now: now,
        boardingDistanceM: 220,
        failWalkingFor: const {'G-10 Markaz'},
        spokenDestination: 'PIMS',
        onResult: (value) => result = value,
      );

      expect(find.textContaining('G-10 Markaz'), findsWidgets);
      expect(find.textContaining('Shaheen Chowk'), findsNothing);
      expect(find.textContaining('FR-07'), findsWidgets);
      expect(
        find.textContaining('Navigation will guide you to the estimated boarding kerb'),
        findsOneWidget,
      );
      await tester.drag(find.byType(ListView), const Offset(0, -900));
      await tester.pumpAndSettle();
      await tester.runAsync(() => VoiceCommands.shared.dispatch('yes'));
      await tester.pumpAndSettle();

      expect(result?.destination.name, 'G-10 Markaz');
      expect(result?.busPlan?.boarding.name, 'G-10 Markaz');
      expect(result?.busPlan?.exit.key, 'pims');
    },
  );

  testWidgets('offers terminals-only guidance for Quaid Azam University', (
    tester,
  ) async {
    TripWalk? result;
    await _openPlanner(
      tester,
      origin: const LatLng(33.743403, 73.109381),
      now: DateTime.utc(2026, 11, 8, 1, 10),
      boardingDistanceM: 40,
      spokenDestination: 'Quaid Azam University',
      onResult: (value) => result = value,
    );

    expect(find.textContaining('FR-04A'), findsWidgets);
    expect(
      find.textContaining('Only the published start and end terminals'),
      findsWidgets,
    );
    await tester.runAsync(() => VoiceCommands.shared.dispatch('yes'));
    await tester.pumpAndSettle();

    // Guidance walks to the boarding terminal, not the exit.
    expect(result?.destination.name, 'Bari Imam');
    expect(result?.busPlan?.route, 'FR-04A');
    expect(result?.busPlan?.boarding.name, 'Bari Imam');
    expect(result?.busPlan?.exit.name, 'Quaid Azam University');
    expect(result?.busPlan?.terminalsOnly, isTrue);
  });
}

Future<void> _openPlanner(
  WidgetTester tester, {
  required LatLng origin,
  required DateTime now,
  required double boardingDistanceM,
  bool walkingRouteUnavailable = false,
  Set<String> failWalkingFor = const {},
  String spokenDestination = 'Karachi Company',
  required void Function(TripWalk?) onResult,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () async {
              onResult(
                await Navigator.of(context).push<TripWalk>(
                  MaterialPageRoute(
                    builder: (_) => DestinationTripScreen(
                      now: () => now,
                      locate: () async => origin,
                      walkingRoute: (from, destination) async {
                        if (walkingRouteUnavailable ||
                            failWalkingFor.contains(destination.name)) {
                          throw Exception('Walking route unavailable');
                        }
                        final distanceM = destination.name == 'G-10 Markaz'
                            ? boardingDistanceM
                            : const Distance()(from, destination.location) +
                                  3000;
                        return NavRoute(
                          geometry: [from, destination.location],
                          steps: const [],
                          distanceM: distanceM,
                          durationS: 180,
                          destination: destination,
                        );
                      },
                    ),
                  ),
                ),
              );
            },
            child: const Text('Open planner'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('Open planner'));
  await tester.pumpAndSettle();
  await tester.runAsync(
    () => VoiceCommands.shared.dispatch(spokenDestination),
  );
  await tester.pumpAndSettle();
}

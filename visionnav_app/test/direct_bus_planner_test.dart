import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/direct_bus_planner.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'FR-07 picks a boarding stop before Karachi Company in each direction',
    () async {
      final planner = await DirectBusPlanner.load();
      final fromWest = planner.plan(
        'Karachi Company',
        const LatLng(33.676728, 73.014472),
      );
      expect(fromWest?.boarding.name, 'G-10 Markaz');
      expect(fromWest?.toward, 'PIMS Hospital');
      expect(fromWest?.exit.name, 'Karachi Company');

      final fromKarachiCompany = planner.plan(
        'G-10 Markaz',
        const LatLng(33.689317, 73.034402),
      );
      expect(fromKarachiCompany?.boarding.name, 'Karachi Company');
      expect(fromKarachiCompany?.toward, 'Police Foundation Metro Station');
      expect(fromKarachiCompany?.exit.name, 'G-10 Markaz');
    },
  );

  test('G-10 to PIMS selects FR-07 toward PIMS, not FR-03A', () async {
    final planner = await DirectBusPlanner.load();
    final plan = planner.plan('PIMS', const LatLng(33.676728, 73.014472));

    expect(plan?.route, 'FR-07');
    expect(plan?.toward, 'PIMS Hospital');
    expect(plan?.boarding.name, 'G-10 Markaz');
    expect(plan?.exit.key, 'pims');
  });

  test(
    'timed PIMS trip from G-10 still boards at G-10, not Shaheen Chowk',
    () async {
      final planner = await DirectBusPlanner.load();
      const origin = LatLng(33.676728, 73.014472);
      final options = planner.journeys(
        'PIMS',
        origin,
        now: DateTime.utc(2026, 11, 8, 7),
        includeTransfers: true,
      );

      expect(options, isNotEmpty);
      expect(options.first.firstLeg.boarding.name, 'G-10 Markaz');
      expect(options.first.firstLeg.route, 'FR-07');
      expect(options.first.firstLeg.exit.key, 'pims');
      expect(
        options.first.firstLeg.boardingDistanceM,
        lessThan(500),
        reason: 'must not prefer Shaheen Chowk (~4.6 km)',
      );
    },
  );

  test(
    'returns a boarding stop for a supported destination regardless of distance',
    () async {
      final planner = await DirectBusPlanner.load();
      const atKarachiCompany = LatLng(33.689317, 73.034402);
      expect(planner.serves('Karachi Company bus stop'), isTrue);
      expect(planner.serves('Faisal Mosque'), isFalse);
      final distant = planner.plan(
        'Karachi Company',
        const LatLng(33.61, 73.12),
      );
      expect(distant?.exit.name, 'Karachi Company');
      expect(distant?.boardingDistanceM, greaterThan(1000));
      expect(distant?.summary, contains('straight-line distance'));
      expect(
        planner.plan('Karachi Company', atKarachiCompany)?.boarding.key,
        isNot('karachi company'),
      );
    },
  );

  test(
    'uses stop-specific Islamabad departures and rejects a missed last bus',
    () async {
      final planner = await DirectBusPlanner.load();
      final plan = planner.plan(
        'Karachi Company',
        const LatLng(33.676728, 73.014472),
      )!;
      final now = DateTime.utc(2026, 11, 8, 17, 8); // 22:08 in Islamabad.
      expect(plan.nextDeparture(now), DateTime.utc(2026, 11, 8, 17, 10, 48));
      expect(
        plan.nextDeparture(now, timeToBoard: const Duration(minutes: 4)),
        isNull,
      );
      expect(plan.nextDeparture(DateTime.utc(2026, 11, 8, 18, 15)), isNull);
      // 00:00 in Islamabad, even though the UTC calendar still says November 8.
      expect(
        plan.nextDeparture(DateTime.utc(2026, 11, 8, 19)),
        DateTime.utc(2026, 11, 9, 1, 20, 48),
      );
    },
  );
  test('G-11 sign does not confirm an exit beyond G-11', () async {
    final planner = await DirectBusPlanner.load();
    const origin = LatLng(33.689317, 73.034402);
    expect(
      planner.plan('G-10 Markaz', origin)?.scannerTrip.direction,
      'fr_7_toward_g11',
    );
    final nust = planner.plan('NUST', origin)!.scannerTrip;
    expect(nust.code, 'FR-7');
    expect(nust.direction, isNull);
  });
  test('plans a route outside FR-07 using the official stop name', () async {
    final planner = await DirectBusPlanner.load();
    // Catalog has 22 labels; index-conflict and incomplete routes use terminals-only.
    expect(planner.routeCount, 22);
    final trip = planner.plan(
      'Hassan Abdal',
      const LatLng(33.783647, 72.723710),
    );
    expect(trip?.route, 'FR-12');
    expect(trip?.boarding.key, 'basti');
    expect(trip?.exit.key, 'hasaan abdal');
    expect(trip?.departures, isNotEmpty);
    expect(planner.serves('Quaid Azam University'), isTrue);
    final qau = planner.plan(
      'Quaid Azam University',
      const LatLng(33.743403, 73.109381),
    );
    expect(qau?.route, 'FR-04A');
    expect(qau?.terminalsOnly, isTrue);
    expect(qau?.boarding.key, 'bari imam');
    expect(qau?.exit.key, 'quaid azam university');
  });

  test('estimates left-hand boarding kerb from route direction', () async {
    final planner = await DirectBusPlanner.load();
    final trip = planner.plan(
      'Karachi Company',
      const LatLng(33.689317, 73.034402),
    );
    expect(trip, isNotNull);
    expect(trip!.travelBearingDeg, isNotNull);
    expect(trip.approachBearingDeg, isNotNull);
    expect(
      (trip.approachBearingDeg! - trip.travelBearingDeg! + 360) % 360,
      closeTo(180, 0.01),
    );
    expect(trip.boardingCurbLocation, isNotNull);
    expect(trip.boardingWalkLocation, isNot(trip.boarding.location));
    expect(
      trip.roadSideGuidanceSpeech,
      contains('left-hand kerb'),
    );
    expect(
      trip.facingCoachSpeech(headingDeg: (trip.approachBearingDeg! + 180) % 360),
      contains('behind you'),
    );
  });

  test(
    'chooses the earlier remaining bus when routes share a boarding stop',
    () async {
      final planner = await DirectBusPlanner.load();
      final trip = planner.plan(
        'G-9 Markaz',
        const LatLng(33.689317, 73.034402),
        now: DateTime.utc(2026, 11, 8, 1, 10),
      );
      expect(trip?.boarding.key, 'karachi company');
      expect(trip?.route, 'FR-07');
    },
  );

  test('finds a scheduled FRB-01 to FR-01 transfer at Khanna Pul', () async {
    final planner = await DirectBusPlanner.load();
    final options = planner.journeys(
      'NUST',
      const LatLng(33.612997, 73.126091),
      now: DateTime.utc(2026, 11, 8, 5),
      initialBoardingKey: 'gangal',
      includeTransfers: true,
    );
    final transfer = options.firstWhere(
      (itinerary) =>
          itinerary.legs.length == 2 &&
          itinerary.legs[0].route == 'FRB-01' &&
          itinerary.legs[0].toward == 'PIMS' &&
          itinerary.legs[1].route == 'FR-01' &&
          itinerary.legs[1].toward == 'Nust Metro Station',
    );

    expect(transfer.legs[0].boarding.key, 'gangal');
    expect(transfer.legs[0].exit.key, 'khanna pul');
    expect(transfer.legs[1].boarding.key, 'khanna pul');
    expect(transfer.legs[0].scheduledArrivalAtExit, isNotNull);
    expect(
      transfer.legs[1].scheduledDeparture!.isAfter(
        transfer.legs[0].scheduledArrivalAtExit!,
      ),
      isTrue,
    );
    expect(transfer.legs[0].route, isNot(transfer.legs[1].route));
  });

  test(
    'does not invent an itinerary from unsupported or late service data',
    () async {
      final planner = await DirectBusPlanner.load();
      const origin = LatLng(33.612997, 73.126091);

      expect(planner.serves('Completely Fake Stop XYZ'), isFalse);
      expect(planner.journeys('Completely Fake Stop XYZ', origin), isEmpty);
      expect(
        planner.journeys(
          'NUST',
          origin,
          now: DateTime.utc(2026, 11, 8, 18, 30),
          initialBoardingKey: 'gangal',
          includeTransfers: true,
        ),
        isEmpty,
      );
    },
  );
  test('matches typed and spoken sector spellings to G-10 Markaz', () async {
    final planner = await DirectBusPlanner.load();
    const origin = LatLng(33.689317, 73.034402);
    for (final name in [
      'G10 Markaz',
      'G 10 Markaz',
      'G-10 Markaz',
      'G ten Markaz',
    ]) {
      expect(planner.serves(name), isTrue, reason: name);
      expect(
        planner.plan(name, origin)?.exit.name,
        'G-10 Markaz',
        reason: name,
      );
      expect(planner.plan(name, origin)?.route, 'FR-07', reason: name);
    }
    expect(planner.serves('G99 Markaz'), isFalse);
  });
}

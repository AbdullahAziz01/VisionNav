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
      expect(distant?.summary, contains('in a straight line'));
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
    expect(planner.routeCount, 15);
    final trip = planner.plan(
      'Hassan Abdal',
      const LatLng(33.783647, 72.723710),
    );
    expect(trip?.route, 'FR-12');
    expect(trip?.boarding.key, 'basti');
    expect(trip?.exit.key, 'hasaan abdal');
    expect(trip?.departures, isNotEmpty);
    expect(planner.listsStop('Quaid Azam University'), isTrue);
    expect(planner.serves('Quaid Azam University'), isFalse);
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
}

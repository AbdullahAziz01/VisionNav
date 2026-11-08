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
    'rejects unsupported destinations, far origins, and boarding at the exit',
    () async {
      final planner = await DirectBusPlanner.load();
      const atKarachiCompany = LatLng(33.689317, 73.034402);
      expect(planner.serves('Karachi Company bus stop'), isTrue);
      expect(planner.serves('Faisal Mosque'), isFalse);
      expect(planner.plan('Karachi Company', const LatLng(0, 0)), isNull);
      expect(planner.plan('Karachi Company', atKarachiCompany), isNull);
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
}

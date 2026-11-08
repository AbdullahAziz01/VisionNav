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
}

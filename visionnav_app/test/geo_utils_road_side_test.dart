import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/navigation/geo_utils.dart';

void main() {
  test('estimated boarding curb offsets left of travel for LHT', () {
    // Travel due north from stop; left kerb is west.
    const stop = LatLng(33.6750, 73.0130);
    const next = LatLng(33.6760, 73.0130);
    final curb = GeoUtils.estimatedBoardingCurb(
      stop: stop,
      nextAlongRoute: next,
      offsetM: 18,
    );
    expect(curb.latitude, closeTo(stop.latitude, 0.0002));
    expect(curb.longitude, lessThan(stop.longitude));
    expect(GeoUtils.distanceM(stop, curb), closeTo(18, 1));
    expect(GeoUtils.speakCompass(0), 'north');
    expect(GeoUtils.speakCompass(90), 'east');
  });
}

import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/navigation/geo_utils.dart';
import 'package:visionnav_app/services/navigation/guidance_engine.dart';
import 'package:visionnav_app/services/navigation/route_models.dart';
import 'package:visionnav_app/services/navigation/routing_service.dart';

// ~1e-5 deg latitude ≈ 1.11 m. Build an L-shaped route:
// start → 200 m north → corner → 100 m east → destination.
const _start = LatLng(33.7000, 73.0000);
const _corner = LatLng(33.7018, 73.0000); // ~200 m north
const _end = LatLng(33.7018, 73.00108); // ~100 m east of corner

LatLng _north(LatLng p, double metres) => LatLng(p.latitude + metres / 111320.0, p.longitude);
LatLng _east(LatLng p, double metres) =>
    LatLng(p.latitude, p.longitude + metres / (111320.0 * 0.8317)); // cos(33.7°)

NavRoute _lRoute() {
  const dest = Place(name: 'Test Stop', location: _end);
  return NavRoute(
    geometry: const [_start, _corner, _end],
    steps: const [
      RouteStep(
        instruction: 'Head north on Test Road',
        distanceM: 200,
        durationS: 150,
        location: _start,
        startIndex: 0,
        endIndex: 1,
        type: 11,
      ),
      RouteStep(
        instruction: 'Turn right onto Station Road',
        distanceM: 100,
        durationS: 75,
        location: _corner,
        startIndex: 1,
        endIndex: 2,
        type: 1,
      ),
      RouteStep(
        instruction: 'Arrive at your destination',
        distanceM: 0,
        durationS: 0,
        location: _end,
        startIndex: 2,
        endIndex: 2,
        type: 10,
      ),
    ],
    distanceM: 300,
    durationS: 225,
    destination: dest,
  );
}

void main() {
  group('GeoUtils', () {
    test('haversine distance is ~200 m for the north leg', () {
      final d = GeoUtils.distanceM(_start, _corner);
      expect(d, closeTo(200, 3));
    });

    test('distance to polyline is ~0 on the line and grows off it', () {
      final geom = _lRoute().geometry;
      final on = GeoUtils.distanceToPolyline(_north(_start, 100), geom);
      expect(on.distanceM, lessThan(1));
      expect(on.segmentIndex, 0);

      final off = GeoUtils.distanceToPolyline(_east(_north(_start, 100), 50), geom);
      expect(off.distanceM, closeTo(50, 3));
    });

    test('speakDistance rounds sensibly', () {
      expect(GeoUtils.speakDistance(37), '35 metres');
      expect(GeoUtils.speakDistance(184), '180 metres');
      expect(GeoUtils.speakDistance(640), '650 metres');
      expect(GeoUtils.speakDistance(1234), '1.2 kilometres');
      expect(GeoUtils.speakDuration(225), 'about 4 minutes');
    });
  });

  group('GuidanceEngine', () {
    test('start speaks destination, distance, duration and first instruction', () {
      final e = GuidanceEngine(_lRoute());
      final ev = e.start();
      expect(ev.type, GuidanceEventType.start);
      expect(ev.speech, contains('Test Stop'));
      expect(ev.speech, contains('300 metres'));
      expect(ev.speech, contains('Head north on Test Road'));
    });

    test('walking the route yields approach → instruction → arrived in order', () {
      final e = GuidanceEngine(_lRoute());
      e.start();
      final spoken = <GuidanceEventType>[];

      // Walk north in 10 m steps up to the corner.
      for (var m = 10.0; m <= 200; m += 10) {
        for (final ev in e.update(_north(_start, m))) {
          spoken.add(ev.type);
        }
      }
      expect(spoken, contains(GuidanceEventType.approach));
      expect(spoken, contains(GuidanceEventType.instruction));
      expect(spoken.indexOf(GuidanceEventType.approach),
          lessThan(spoken.indexOf(GuidanceEventType.instruction)));
      expect(e.currentStep, 1);

      // Walk east to the destination.
      for (var m = 10.0; m <= 100; m += 10) {
        for (final ev in e.update(_east(_corner, m))) {
          spoken.add(ev.type);
        }
      }
      expect(spoken.last, GuidanceEventType.arrived);
      expect(e.arrived, isTrue);
      expect(e.update(_end), isEmpty); // no more events after arrival
    });

    test('approach phrase includes distance and lower-cased instruction', () {
      final e = GuidanceEngine(_lRoute());
      e.start();
      final events = e.update(_north(_start, 165)); // 35 m before the corner
      expect(events, hasLength(1));
      expect(events.single.type, GuidanceEventType.approach);
      expect(events.single.speech, 'In 35 metres, turn right onto Station Road.');
    });

    test('off-route is reported only after consecutive far fixes', () {
      final e = GuidanceEngine(_lRoute(), offRouteConsecutive: 3);
      e.start();
      final far = _east(_north(_start, 100), 60); // 60 m off the line
      expect(e.update(far), isEmpty);
      expect(e.update(far), isEmpty);
      final third = e.update(far);
      expect(third.single.type, GuidanceEventType.offRoute);
      expect(e.offRoute, isTrue);
      // Back on route clears the flag without speaking.
      expect(e.update(_north(_start, 100)), isEmpty);
      expect(e.offRoute, isFalse);
    });

    test('progress reminder fires on long straight stretches', () {
      final e = GuidanceEngine(_lRoute(), progressIntervalM: 50);
      e.start();
      final events = e.update(_north(_start, 60));
      expect(events.single.type, GuidanceEventType.progress);
      expect(events.single.speech, startsWith('Continue for'));
    });
  });

  group('ORS parser', () {
    test('parses geometry, summary and steps from GeoJSON', () {
      final json = {
        'features': [
          {
            'geometry': {
              'coordinates': [
                [73.0, 33.7],
                [73.0, 33.7018],
                [73.00108, 33.7018],
              ],
            },
            'properties': {
              'summary': {'distance': 300.0, 'duration': 225.0},
              'segments': [
                {
                  'steps': [
                    {
                      'distance': 200.0,
                      'duration': 150.0,
                      'type': 11,
                      'instruction': 'Head north',
                      'name': '-',
                      'way_points': [0, 1],
                    },
                    {
                      'distance': 100.0,
                      'duration': 75.0,
                      'type': 1,
                      'instruction': 'Turn right onto Station Road',
                      'name': 'Station Road',
                      'way_points': [1, 2],
                    },
                    {
                      'distance': 0.0,
                      'duration': 0.0,
                      'type': 10,
                      'instruction': 'Arrive at your destination',
                      'name': '-',
                      'way_points': [2, 2],
                    },
                  ],
                },
              ],
            },
          },
        ],
      };
      final route = OrsRoutingService.parseOrsGeoJson(
        json,
        const Place(name: 'X', location: _end),
      );
      expect(route.geometry, hasLength(3));
      expect(route.distanceM, 300);
      expect(route.steps, hasLength(3));
      expect(route.steps[1].location.latitude, closeTo(33.7018, 1e-9));
      expect(route.steps[1].streetName, 'Station Road');
      expect(route.steps.last.isArrival, isTrue);
    });
  });
}

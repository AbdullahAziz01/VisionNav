import 'package:flutter_test/flutter_test.dart';
import 'package:visionnav_app/services/announcement_manager.dart';
import 'package:visionnav_app/services/pipeline_models.dart';

TrackedDetection det(int id, String cls, double? d) => TrackedDetection(
      trackId: id,
      className: cls,
      confidence: 0.9,
      bboxXyxy: const [0, 0, 10, 10],
      estimatedDistanceM: d,
      distanceLabel: '',
    );

void main() {
  late DateTime clock;
  late AnnouncementManager m;

  setUp(() {
    clock = DateTime(2026, 1, 1, 12);
    m = AnnouncementManager(
      perTrackCooldown: const Duration(seconds: 5),
      globalMinGap: const Duration(seconds: 2),
      distanceChangeThresholdM: 1.0,
      trackExpiry: const Duration(seconds: 10),
      now: () => clock,
    );
  });

  void tick(Duration d) => clock = clock.add(d);

  group('describe', () {
    test('formats whole, half and sub-metre distances', () {
      expect(AnnouncementManager.describe('person', 3.1),
          'Person approximately 3 meters away.');
      expect(AnnouncementManager.describe('bus', 2.6),
          'Bus approximately 2.5 meters away.');
      expect(AnnouncementManager.describe('car', 1.2),
          'Car approximately 1 meter away.');
      expect(AnnouncementManager.describe('person', 0.6),
          'Person less than 1 meter away.');
    });
  });

  test('announces a new track once, then stays silent on repeat frames', () {
    expect(m.next([det(1, 'person', 3.0)]), isNotNull);
    tick(const Duration(milliseconds: 500));
    expect(m.next([det(1, 'person', 3.0)]), isNull);
    tick(const Duration(seconds: 6)); // cooldown passed, distance unchanged
    expect(m.next([det(1, 'person', 3.0)]), isNull);
  });

  test('re-announces after cooldown when distance changed enough', () {
    expect(m.next([det(1, 'person', 4.0)]), isNotNull);
    tick(const Duration(seconds: 3)); // still in cooldown
    expect(m.next([det(1, 'person', 2.5)]), isNull);
    tick(const Duration(seconds: 3)); // cooldown over, moved 1.5 m
    expect(m.next([det(1, 'person', 2.5)]),
        'Person approximately 2.5 meters away.');
  });

  test('speaks the nearest qualifying object first', () {
    final phrase = m.next([det(1, 'bus', 6.0), det(2, 'person', 2.0)]);
    expect(phrase, startsWith('Person'));
  });

  test('global gap prevents back-to-back announcements', () {
    expect(m.next([det(1, 'person', 2.0), det(2, 'bus', 5.0)]), isNotNull);
    tick(const Duration(milliseconds: 800));
    expect(m.next([det(1, 'person', 2.0), det(2, 'bus', 5.0)]), isNull);
    tick(const Duration(seconds: 2));
    expect(m.next([det(1, 'person', 2.0), det(2, 'bus', 5.0)]),
        startsWith('Bus'));
  });

  test('canSpeak=false updates state but consumes nothing', () {
    expect(m.next([det(1, 'person', 2.0)], canSpeak: false), isNull);
    expect(m.next([det(1, 'person', 2.0)]), isNotNull);
  });

  test('objects without a distance are ignored', () {
    expect(m.next([det(1, 'person', null)]), isNull);
  });

  test('a track that disappears and returns is announced again', () {
    expect(m.next([det(1, 'person', 2.0)]), isNotNull);
    tick(const Duration(seconds: 11)); // expired
    expect(m.next([det(1, 'person', 2.0)]), isNotNull);
  });

  TrackedDetection greenBus({
    int id = 7,
    double? distance = 8,
    bool stable = true,
    String? direction = 'toward_barakahu',
    String? message = 'Green Line toward Barakahu.',
    String line = 'Green Line',
  }) {
    return TrackedDetection(
      trackId: id,
      className: 'bus',
      confidence: 0.9,
      bboxXyxy: const [0, 0, 10, 10],
      estimatedDistanceM: distance,
      distanceLabel: '',
      routeLine: line,
      routeDestination: 'Barakahu',
      routeDirection: direction,
      routeConfidence: 1,
      routeIsStable: stable,
      routeTtsMessage: message,
    );
  }

  test('stable Green Line route is selected before a distance phrase', () {
    final phrase = m.next([
      det(1, 'person', 2.0),
      greenBus(),
    ]);
    expect(phrase, 'Green Line toward Barakahu.');
  });

  test('the same track, route, and direction is announced once only', () {
    final bus = greenBus();
    expect(m.next([bus]), 'Green Line toward Barakahu.');
    tick(const Duration(milliseconds: 500));
    expect(m.next([bus]), isNull);
    tick(const Duration(seconds: 2));
    expect(m.next([bus]), 'Bus approximately 8 meters away.');
  });

  test('a changed direction for the same track is announced once', () {
    expect(m.next([greenBus()]), 'Green Line toward Barakahu.');
    tick(const Duration(seconds: 2));
    expect(
      m.next([
        greenBus(
          direction: 'toward_n5',
          line: 'Orange Line',
          message: 'Orange Line toward N-5.',
        ),
      ]),
      'Orange Line toward N-5.',
    );
    tick(const Duration(milliseconds: 500));
    expect(
      m.next([
        greenBus(
          direction: 'toward_n5',
          line: 'Orange Line',
          message: 'Orange Line toward N-5.',
        ),
      ]),
      isNull,
    );
  });

  test('an unstable route does not announce', () {
    expect(
      m.next([greenBus(stable: false, distance: 4)]),
      'Bus approximately 4 meters away.',
    );
    tick(const Duration(seconds: 6));
    expect(
      m.next([
        greenBus(stable: true, message: '   ', distance: 6),
      ]),
      'Bus approximately 6 meters away.',
    );
  });

  test('person and bus distance phrases still work without a stable route', () {
    expect(m.next([det(1, 'person', 3.0)]),
        'Person approximately 3 meters away.');
    tick(const Duration(seconds: 2));
    expect(m.next([det(2, 'bus', 5.0)]), 'Bus approximately 5 meters away.');
  });

  test('a bus that leaves and returns can be announced again', () {
    expect(m.next([greenBus()]), 'Green Line toward Barakahu.');
    tick(const Duration(seconds: 2));
    expect(m.next([det(1, 'person', 3.0)]),
        'Person approximately 3 meters away.');
    tick(const Duration(seconds: 2));
    expect(m.next([greenBus()]), 'Green Line toward Barakahu.');
  });

  test('missing route JSON fields do not crash parsing', () {
    final parsed = TrackedDetection.fromJson({
      'track_id': 3,
      'class': 'bus',
      'confidence': 0.8,
      'bbox_xyxy': [1, 2, 3, 4],
      'estimated_distance_m': 5,
      'distance_label': '5.0 m (estimated metric)',
    });
    expect(parsed.className, 'bus');
    expect(parsed.routeLine, isNull);
    expect(parsed.routeCode, isNull);
    expect(parsed.routeDestination, isNull);
    expect(parsed.routeDirection, isNull);
    expect(parsed.routeConfidence, isNull);
    expect(parsed.routeIsStable, isFalse);
    expect(parsed.routeTtsMessage, isNull);

    final oddTypes = TrackedDetection.fromJson({
      'track_id': 4,
      'class': 'person',
      'confidence': 0.5,
      'bbox_xyxy': [0, 0, 1, 1],
      'route_line': 12,
      'route_code': 4,
      'route_confidence': 'high',
      'route_is_stable': 'yes',
      'route_tts_message': null,
    });
    expect(oddTypes.routeLine, isNull);
    expect(oddTypes.routeCode, isNull);
    expect(oddTypes.routeConfidence, isNull);
    expect(oddTypes.routeIsStable, isFalse);
    expect(oddTypes.routeTtsMessage, isNull);

    final stable = TrackedDetection.fromJson({
      'track_id': 7,
      'class': 'bus',
      'confidence': 0.85,
      'bbox_xyxy': [10, 20, 220, 140],
      'route_line': 'Green Line',
      'route_destination': 'Barakahu',
      'route_direction': 'toward_barakahu',
      'route_confidence': 1,
      'route_is_stable': true,
      'route_tts_message': 'Green Line toward Barakahu.',
    });
    expect(stable.routeLine, 'Green Line');
    expect(stable.routeCode, isNull);
    expect(stable.routeDestination, 'Barakahu');
    expect(stable.routeDirection, 'toward_barakahu');
    expect(stable.routeConfidence, 1);
    expect(stable.routeIsStable, isTrue);
    expect(stable.routeTtsMessage, 'Green Line toward Barakahu.');

    final routeOnly = TrackedDetection.fromJson({
      'track_id': 8,
      'class': 'bus',
      'confidence': 0.9,
      'bbox_xyxy': [0, 0, 10, 10],
      'route_line': 'FR-7',
      'route_code': 'FR-7',
      'route_destination': null,
      'route_direction': null,
      'route_is_stable': true,
      'route_tts_message':
          'Feeder route seven detected. Direction could not be read.',
    });
    expect(routeOnly.routeCode, 'FR-7');
    expect(routeOnly.routeDirection, isNull);
    expect(routeOnly.routeDestination, isNull);
    expect(routeOnly.routeIsStable, isTrue);
  });

  TrackedDetection feederBus({
    String? direction,
    String message =
        'Feeder route seven detected. Direction could not be read.',
    double? distance = 8,
  }) {
    return TrackedDetection(
      trackId: 4,
      className: 'bus',
      confidence: 0.9,
      bboxXyxy: const [0, 0, 10, 10],
      estimatedDistanceM: distance,
      distanceLabel: '',
      routeLine: 'FR-7',
      routeCode: 'FR-7',
      routeDestination: direction == null ? null : 'G-11',
      routeDirection: direction,
      routeConfidence: 1,
      routeIsStable: true,
      routeTtsMessage: message,
    );
  }

  test('a route-only result is spoken once even when direction is null', () {
    final bus = feederBus();
    expect(
      m.next([bus]),
      'Feeder route seven detected. Direction could not be read.',
    );
    tick(const Duration(milliseconds: 500));
    expect(m.next([bus]), isNull);
    tick(const Duration(seconds: 2));
    expect(m.next([bus]), 'Bus approximately 8 meters away.');
  });

  test('a later confirmed direction is announced once', () {
    expect(
      m.next([feederBus()]),
      'Feeder route seven detected. Direction could not be read.',
    );
    tick(const Duration(seconds: 2));
    expect(
      m.next([
        feederBus(
          direction: 'fr_7_toward_g11',
          message: 'Feeder route seven toward G-11.',
        ),
      ]),
      'Feeder route seven toward G-11.',
    );
    tick(const Duration(milliseconds: 500));
    expect(
      m.next([
        feederBus(
          direction: 'fr_7_toward_g11',
          message: 'Feeder route seven toward G-11.',
        ),
      ]),
      isNull,
    );
  });

  test('a feeder that leaves can be announced again', () {
    expect(
      m.next([feederBus()]),
      'Feeder route seven detected. Direction could not be read.',
    );
    tick(const Duration(seconds: 2));
    expect(m.next([det(1, 'person', 3.0)]),
        'Person approximately 3 meters away.');
    tick(const Duration(seconds: 2));
    expect(
      m.next([feederBus()]),
      'Feeder route seven detected. Direction could not be read.',
    );
  });

  test('distance alerts continue when the route is not identified', () {
    expect(m.next([det(4, 'bus', 4.0)]), 'Bus approximately 4 meters away.');
    tick(const Duration(seconds: 6));
    expect(
      m.next([
        feederBus(
          message: '   ',
          distance: 2.0,
        ),
      ]),
      'Bus approximately 2 meters away.',
    );
  });
}

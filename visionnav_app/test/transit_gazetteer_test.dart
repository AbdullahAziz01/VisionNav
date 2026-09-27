import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/navigation/transit_gazetteer.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('bundled asset', () {
    late TransitGazetteer gaz;

    setUp(() => gaz = TransitGazetteer());

    test('asset loads and contains the Metro Bus network', () async {
      final stops = await gaz.load();
      expect(stops.length, greaterThan(150));
      expect(stops.where((s) => s.isMetro).length, greaterThan(25));
    });

    test('spoken bus-stand phrasing finds the real station', () async {
      // These all failed against OSM free-text search.
      final pims = await gaz.find('PIMS bus stand');
      expect(pims, isNotNull);
      expect(pims!.name, contains('PIMS'));
      expect(pims.location.latitude, closeTo(33.7059, 0.002));

      final chaman = await gaz.find('Chaman metro bus stand');
      expect(chaman, isNotNull);
      expect(chaman!.name.toLowerCase(), contains('chaman'));

      final faizabad = await gaz.find('Faizabad metro station');
      expect(faizabad, isNotNull);
      expect(faizabad!.name.toLowerCase(), contains('faizabad'));

      final secretariat = await gaz.find('Secretariat bus stand');
      expect(secretariat, isNotNull);
      expect(secretariat!.name.toLowerCase(), contains('secretariat'));

      final kachehri = await gaz.find('Katchery metro station');
      expect(kachehri, isNotNull);
      expect(kachehri!.name.toLowerCase(), contains('katchery'));
    });

    test('bare station name works, with or without filler words', () async {
      for (final phrase in [
        'PIMS',
        'pims station',
        'take me to PIMS bus stop',
        'go to the PIMS metro station please',
      ]) {
        final p = await gaz.find(phrase);
        expect(p, isNotNull, reason: 'failed for "$phrase"');
        expect(p!.name, contains('PIMS'), reason: 'wrong stop for "$phrase"');
      }
    });

    test('unrelated places are rejected so the online geocoder can try', () async {
      expect(await gaz.find('Centaurus Mall'), isNull);
      expect(await gaz.find('zzzz nowhere'), isNull);
      expect(await gaz.find('bus stand'), isNull); // no identity words at all
    });
  });

  group('matching rules', () {
    late TransitGazetteer gaz;

    setUp(() {
      gaz = TransitGazetteer();
      gaz.loadFromStops(const [
        TransitStop(
          name: 'Metro Bus Terminal Saddar',
          key: 'saddar',
          location: LatLng(33.5935, 73.0561),
          isMetro: true,
        ),
        TransitStop(
          name: 'Saddar Kerbside Stop',
          key: 'saddar kerbside',
          location: LatLng(33.5900, 73.0500),
          isMetro: false,
        ),
        TransitStop(
          name: 'Metro Bus Terminal Faizabad',
          key: 'faizabad',
          location: LatLng(33.6613, 73.0829),
          isMetro: true,
        ),
      ]);
    });

    test('prefers the Metro station over a kerbside stop', () async {
      final p = await gaz.find('saddar');
      expect(p!.name, 'Metro Bus Terminal Saddar');
    });

    test('nearby stop wins when names are equally good', () async {
      final p = await gaz.find('faizabad', near: const LatLng(33.66, 73.08));
      expect(p!.name, contains('Faizabad'));
    });

    test('coreTokens strips generic transport words', () {
      expect(TransitGazetteer.coreTokens('PIMS Metro Bus Station North'), ['pims']);
      expect(TransitGazetteer.coreTokens('take me to Chaman bus stand'), ['chaman']);
      expect(TransitGazetteer.coreTokens('bus station'), isEmpty);
    });
  });

  test('asset JSON is well formed and coordinates are in-region', () async {
    final raw = await rootBundle.loadString('assets/transit_stops.json');
    final json = jsonDecode(raw) as Map<String, dynamic>;
    final stops = json['stops'] as List<dynamic>;
    expect(json['count'], stops.length);
    for (final s in stops.whereType<Map<String, dynamic>>()) {
      final lat = (s['lat'] as num).toDouble();
      final lon = (s['lon'] as num).toDouble();
      expect(lat, inInclusiveRange(33.40, 33.80));
      expect(lon, inInclusiveRange(72.80, 73.30));
      expect((s['name'] as String).trim(), isNotEmpty);
    }
  });
}

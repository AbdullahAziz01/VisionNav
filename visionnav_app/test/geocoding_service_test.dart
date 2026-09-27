import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/navigation/geocoding_service.dart';

void main() {
  test('falls back to a stripped query when the full phrase finds nothing', () async {
    final queries = <String>[];
    final client = MockClient((req) async {
      final q = req.url.queryParameters['q']!;
      queries.add(q);
      if (q.toLowerCase().contains('bus stand')) return http.Response('[]', 200);
      return http.Response(
        jsonEncode([
          {'lat': '33.66', 'lon': '73.08', 'name': 'Faizabad', 'display_name': 'Faizabad, Islamabad'},
        ]),
        200,
      );
    });
    final geo = NominatimGeocodingService(client: client);
    final place = await geo.geocode('Faizabad bus stand');
    expect(queries, ['Faizabad bus stand', 'Faizabad']);
    expect(place.name, 'Faizabad');
    expect(place.location, const LatLng(33.66, 73.08));
  });

  test('prefers the result nearest to the user', () async {
    final client = MockClient((req) async => http.Response(
          jsonEncode([
            {'lat': '31.57', 'lon': '74.33', 'name': 'Railway Station', 'display_name': 'Lahore'},
            {'lat': '33.60', 'lon': '73.05', 'name': 'Railway Station', 'display_name': 'Rawalpindi'},
          ]),
          200,
        ));
    final geo = NominatimGeocodingService(client: client);
    final place = await geo.geocode('railway station', near: const LatLng(33.6, 73.0));
    expect(place.displayName, 'Rawalpindi');
  });

  test('throws a spoken-friendly error when nothing is found', () async {
    final client = MockClient((_) async => http.Response('[]', 200));
    final geo = NominatimGeocodingService(client: client);
    expect(
      () => geo.geocode('xyzzy'),
      throwsA(isA<GeocodingException>().having((e) => e.message, 'message', contains('could not find'))),
    );
  });
}

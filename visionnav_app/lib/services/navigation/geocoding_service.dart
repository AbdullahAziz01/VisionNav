import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/navigation/navigation_config.dart';
import 'package:visionnav_app/services/navigation/route_models.dart';
import 'package:visionnav_app/services/navigation/transit_gazetteer.dart';

class GeocodingException implements Exception {
  GeocodingException(this.message);
  final String message;
  @override
  String toString() => message;
}

abstract class GeocodingService {
  /// Resolve free text ("Saddar bus stand") to a place. [near] biases results.
  Future<Place> geocode(String query, {LatLng? near});
}

/// OpenStreetMap Nominatim geocoder — no API key.
class NominatimGeocodingService implements GeocodingService {
  NominatimGeocodingService({
    http.Client? client,
    TransitGazetteer? gazetteer,
    this.countryCode = kGeocodeCountryCode,
    this.timeout = const Duration(seconds: 12),
  })  : _client = client ?? http.Client(),
        _gazetteer = gazetteer ?? TransitGazetteer();

  final http.Client _client;

  /// Local bus stands / Metro Bus stations are checked first: the app is for
  /// public transport, and OSM's free-text search misses them (a user saying
  /// "PIMS bus stand" gets nothing, because OSM calls it "PIMS Metro Bus
  /// Station"). Offline, so it also answers instantly with no network.
  final TransitGazetteer _gazetteer;
  final String countryCode;
  final Duration timeout;

  static final Uri _base = Uri.parse('https://nominatim.openstreetmap.org/search');

  /// Words that speech adds but OSM place names rarely contain. If the full
  /// query finds nothing, retry without them ("Faizabad bus stand" → "Faizabad").
  static final RegExp _genericWords = RegExp(
    r'\b(bus\s*stand|bus\s*stop|bus\s*terminal|bus\s*station|stand|stop|terminal|station|the|to)\b',
    caseSensitive: false,
  );

  @override
  Future<Place> geocode(String query, {LatLng? near}) async {
    final q = query.trim();
    if (q.isEmpty) throw GeocodingException('Empty destination.');

    try {
      final stop = await _gazetteer.find(q, near: near);
      if (stop != null) return stop;
    } catch (_) {
      // Asset missing or unreadable — fall through to the online geocoder.
    }

    final attempts = <String>[q];
    final stripped = q.replaceAll(_genericWords, ' ').replaceAll(RegExp(r'\s+'), ' ').trim();
    if (stripped.isNotEmpty && stripped.toLowerCase() != q.toLowerCase()) {
      attempts.add(stripped);
    }

    GeocodingException? lastError;
    for (var i = 0; i < attempts.length; i++) {
      if (i > 0) await Future<void>.delayed(const Duration(milliseconds: 1100)); // Nominatim: ≤1 req/s
      try {
        return await _lookup(attempts[i], near: near);
      } on GeocodingException catch (e) {
        lastError = e;
      }
    }
    throw lastError ?? GeocodingException('I could not find "$q".');
  }

  Future<Place> _lookup(String q, {LatLng? near}) async {
    final params = <String, String>{
      'q': q,
      'format': 'jsonv2',
      'limit': '5',
      'addressdetails': '1',
      'accept-language': 'en',
      if (countryCode.isNotEmpty) 'countrycodes': countryCode,
    };
    if (near != null) {
      // ~50 km box around the user; results inside are ranked first.
      const d = 0.45;
      params['viewbox'] =
          '${near.longitude - d},${near.latitude + d},${near.longitude + d},${near.latitude - d}';
      params['bounded'] = '0';
    }

    final uri = _base.replace(queryParameters: params);
    final res = await _client
        .get(uri, headers: {'User-Agent': kHttpUserAgent, 'Accept': 'application/json'})
        .timeout(timeout);
    if (res.statusCode != 200) {
      throw GeocodingException('Geocoding failed (${res.statusCode}).');
    }
    final list = jsonDecode(res.body);
    if (list is! List || list.isEmpty) {
      throw GeocodingException('I could not find "$q". Try a more specific place name.');
    }

    // Prefer the closest result when we know where the user is.
    Map<String, dynamic> best = list.first as Map<String, dynamic>;
    if (near != null) {
      double bestD = double.infinity;
      for (final item in list.whereType<Map<String, dynamic>>()) {
        final p = _toLatLng(item);
        if (p == null) continue;
        final d = const Distance().as(LengthUnit.Meter, near, p);
        if (d < bestD) {
          bestD = d;
          best = item;
        }
      }
    }

    final loc = _toLatLng(best);
    if (loc == null) throw GeocodingException('Geocoder returned no coordinates.');
    final display = best['display_name'] as String? ?? q;
    return Place(name: _shortName(best, q), displayName: display, location: loc);
  }

  static LatLng? _toLatLng(Map<String, dynamic> item) {
    final lat = double.tryParse('${item['lat']}');
    final lon = double.tryParse('${item['lon']}');
    if (lat == null || lon == null) return null;
    return LatLng(lat, lon);
  }

  static String _shortName(Map<String, dynamic> item, String fallback) {
    final name = item['name'] as String?;
    if (name != null && name.trim().isNotEmpty) return name.trim();
    final display = item['display_name'] as String?;
    if (display != null && display.isNotEmpty) return display.split(',').first.trim();
    return fallback;
  }
}

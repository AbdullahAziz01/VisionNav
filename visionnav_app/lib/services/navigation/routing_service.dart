import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/navigation/navigation_config.dart';
import 'package:visionnav_app/services/navigation/route_models.dart';

class RoutingException implements Exception {
  RoutingException(this.message);
  final String message;
  @override
  String toString() => message;
}

abstract class RoutingService {
  Future<NavRoute> walkingRoute(LatLng from, Place to, {bool shortest = false});
}

/// OpenRouteService pedestrian routing with turn-by-turn instructions.
class OrsRoutingService implements RoutingService {
  OrsRoutingService({
    http.Client? client,
    String? apiKey,
    this.timeout = const Duration(seconds: 20),
  }) : _client = client ?? http.Client(),
       _apiKey = apiKey;

  final http.Client _client;
  final String? _apiKey;
  String get apiKey => _apiKey ?? routingApiKey;
  final Duration timeout;

  static final Uri _endpoint =
      Uri.parse('https://api.heigit.org/openrouteservice/v2/directions/foot-walking/geojson');

  @override
  Future<NavRoute> walkingRoute(LatLng from, Place to, {bool shortest = false}) async {
    final key = apiKey;
    if (key.isEmpty) {
      throw RoutingException(
        'Walking directions need an OpenRouteService key. Add it in Settings.',
      );
    }
    final body = jsonEncode({
      'coordinates': [
        [from.longitude, from.latitude],
        [to.location.longitude, to.location.latitude],
      ],
      'instructions': true,
      'language': 'en',
      'units': 'm',
      'preference': shortest ? 'shortest' : 'recommended',
    });
    final res = await _client
        .post(
          _endpoint,
          headers: {
            'Authorization': key,
            'Content-Type': 'application/json',
            'Accept': 'application/geo+json, application/json',
            'User-Agent': kHttpUserAgent,
          },
          body: body,
        )
        .timeout(timeout);

    if (res.statusCode != 200) {
      String detail = res.body;
      try {
        final err = jsonDecode(res.body);
        detail = err['error']?['message']?.toString() ?? err['error']?.toString() ?? detail;
      } catch (_) {}
      throw RoutingException('Routing failed (${res.statusCode}): $detail');
    }
    return parseOrsGeoJson(jsonDecode(res.body) as Map<String, dynamic>, to);
  }

  /// Exposed for tests.
  static NavRoute parseOrsGeoJson(Map<String, dynamic> json, Place destination) {
    final features = json['features'] as List<dynamic>? ?? const [];
    if (features.isEmpty) throw RoutingException('No route found.');
    final feature = features.first as Map<String, dynamic>;
    final coords = (feature['geometry']?['coordinates'] as List<dynamic>? ?? const [])
        .map((c) => LatLng((c[1] as num).toDouble(), (c[0] as num).toDouble()))
        .toList();
    if (coords.length < 2) throw RoutingException('Route geometry is empty.');

    final props = feature['properties'] as Map<String, dynamic>? ?? const {};
    final summary = props['summary'] as Map<String, dynamic>? ?? const {};
    final segments = props['segments'] as List<dynamic>? ?? const [];

    final steps = <RouteStep>[];
    for (final seg in segments.whereType<Map<String, dynamic>>()) {
      for (final s in (seg['steps'] as List<dynamic>? ?? const []).whereType<Map<String, dynamic>>()) {
        final wp = (s['way_points'] as List<dynamic>? ?? const [0, 0]);
        final startIdx = (wp.isNotEmpty ? wp[0] as num : 0).toInt().clamp(0, coords.length - 1);
        final endIdx = (wp.length > 1 ? wp[1] as num : startIdx).toInt().clamp(0, coords.length - 1);
        steps.add(RouteStep(
          instruction: (s['instruction'] as String? ?? '').trim(),
          distanceM: (s['distance'] as num? ?? 0).toDouble(),
          durationS: (s['duration'] as num? ?? 0).toDouble(),
          location: coords[startIdx],
          startIndex: startIdx,
          endIndex: endIdx,
          streetName: (s['name'] as String? ?? '').trim(),
          type: (s['type'] as num? ?? -1).toInt(),
        ));
      }
    }
    if (steps.isEmpty) throw RoutingException('Route has no instructions.');

    return NavRoute(
      geometry: coords,
      steps: steps,
      distanceM: (summary['distance'] as num? ?? 0).toDouble(),
      durationS: (summary['duration'] as num? ?? 0).toDouble(),
      destination: destination,
    );
  }
}

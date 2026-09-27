import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/services/navigation/route_models.dart';

/// One public-transport stop from the bundled OpenStreetMap extract.
class TransitStop {
  const TransitStop({
    required this.name,
    required this.key,
    required this.location,
    required this.isMetro,
  });

  /// Official OSM name, e.g. "Metro Bus Terminal Chaman".
  final String name;

  /// Identity words only, e.g. "chaman" — generic words like "metro", "bus",
  /// "station", "stand" are stripped so spoken phrasing does not matter.
  final String key;
  final LatLng location;
  final bool isMetro;
}

/// Offline lookup for local bus stands and Metro Bus stations.
///
/// Plain OSM text search fails for how people actually speak: "PIMS bus stand"
/// finds nothing, because OSM calls it "PIMS Metro Bus Station". This gazetteer
/// matches on identity words only, so all of these reach the same stop:
///   "PIMS", "PIMS bus stand", "PIMS metro station", "pims stop"
///
/// Data: OpenStreetMap contributors (ODbL), Islamabad/Rawalpindi extract,
/// bundled as an asset so it works instantly and without a network.
class TransitGazetteer {
  TransitGazetteer({this.assetPath = 'assets/transit_stops.json'});

  final String assetPath;
  List<TransitStop>? _stops;

  /// Generic words that describe the kind of place, not which place it is.
  static const _noise = <String>{
    'metro', 'bus', 'station', 'stop', 'terminal', 'stand', 'adda',
    'north', 'south', 'east', 'west', 'no', 'islamabad', 'rawalpindi',
    'the', 'to', 'go', 'take', 'me', 'please', 'a', 'at', 'of', 'near',
  };

  static String normalize(String s) => s
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9 ]+'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();

  /// Identity words of a phrase, in order, with generic words removed.
  static List<String> coreTokens(String s) =>
      normalize(s).split(' ').where((t) => t.isNotEmpty && !_noise.contains(t)).toList();

  Future<List<TransitStop>> load() async {
    final cached = _stops;
    if (cached != null) return cached;
    final raw = await rootBundle.loadString(assetPath);
    final json = jsonDecode(raw) as Map<String, dynamic>;
    final list = (json['stops'] as List<dynamic>)
        .whereType<Map<String, dynamic>>()
        .map((s) => TransitStop(
              name: s['name'] as String,
              key: s['key'] as String,
              location: LatLng((s['lat'] as num).toDouble(), (s['lon'] as num).toDouble()),
              isMetro: s['metro'] as bool? ?? false,
            ))
        .toList();
    _stops = list;
    return list;
  }

  /// Load from an in-memory list instead of the asset (used by tests).
  void loadFromStops(List<TransitStop> stops) => _stops = stops;

  /// Best matching stop for a spoken phrase, or null if nothing is close
  /// enough. [near] breaks ties between same-named stops.
  Future<Place?> find(String spoken, {LatLng? near}) async {
    final stops = await load();
    final query = coreTokens(spoken);
    if (query.isEmpty) return null;

    TransitStop? best;
    var bestScore = 0.0;
    for (final stop in stops) {
      final score = _score(query, stop, near: near);
      if (score > bestScore) {
        bestScore = score;
        best = stop;
      }
    }
    // Below this, the match is a coincidence rather than the place asked for.
    if (best == null || bestScore < 1.0) return null;
    return Place(
      name: best.name,
      displayName: '${best.name} (public transport stop)',
      location: best.location,
    );
  }

  double _score(List<String> query, TransitStop stop, {LatLng? near}) {
    final target = stop.key.split(' ').where((t) => t.isNotEmpty).toList();
    if (target.isEmpty) return 0;

    final q = query.join(' ');
    final t = target.join(' ');

    double score;
    if (q == t) {
      score = 4.0; // exact identity match: "chaman" == "chaman"
    } else {
      // Count identity words shared in both directions, so a short spoken
      // phrase can still match a longer official name and vice versa.
      final overlap = target.where(query.contains).length;
      if (overlap == 0) return 0;
      final covered = overlap / target.length;
      final used = overlap / query.length;
      score = 2.0 * covered * used;
      // Whole-phrase containment ("g 10" inside "g10 golra") is a strong signal.
      if (t.contains(q) || q.contains(t)) score += 1.0;
    }

    if (stop.isMetro) score += 0.25; // prefer the real Metro station over a kerbside stop
    if (near != null) {
      final km = const Distance().as(LengthUnit.Kilometer, near, stop.location);
      score += 0.5 / (1 + km); // gentle nudge toward the nearer of two same-name stops
    }
    return score;
  }
}

import 'dart:math' as math;

import 'package:latlong2/latlong.dart';

/// Small geodesy helpers used by routing and guidance. Pure Dart.
class GeoUtils {
  GeoUtils._();

  static const double earthRadiusM = 6371000.0;

  static double _rad(double deg) => deg * math.pi / 180.0;
  static double _deg(double rad) => rad * 180.0 / math.pi;

  /// Great-circle distance in metres (haversine).
  static double distanceM(LatLng a, LatLng b) {
    final dLat = _rad(b.latitude - a.latitude);
    final dLon = _rad(b.longitude - a.longitude);
    final la1 = _rad(a.latitude);
    final la2 = _rad(b.latitude);
    final h = math.sin(dLat / 2) * math.sin(dLat / 2) +
        math.cos(la1) * math.cos(la2) * math.sin(dLon / 2) * math.sin(dLon / 2);
    return 2 * earthRadiusM * math.asin(math.min(1.0, math.sqrt(h)));
  }

  /// Initial bearing from [a] to [b] in degrees [0, 360).
  static double bearingDeg(LatLng a, LatLng b) {
    final la1 = _rad(a.latitude);
    final la2 = _rad(b.latitude);
    final dLon = _rad(b.longitude - a.longitude);
    final y = math.sin(dLon) * math.cos(la2);
    final x = math.cos(la1) * math.sin(la2) -
        math.sin(la1) * math.cos(la2) * math.cos(dLon);
    return (_deg(math.atan2(y, x)) + 360.0) % 360.0;
  }

  /// Shortest distance in metres from [p] to the segment [a]-[b].
  /// Uses a local equirectangular projection (accurate for walking scales).
  static double distanceToSegmentM(LatLng p, LatLng a, LatLng b) {
    final lat0 = _rad((a.latitude + b.latitude + p.latitude) / 3.0);
    final cos0 = math.cos(lat0);
    double x(LatLng q) => _rad(q.longitude) * cos0 * earthRadiusM;
    double y(LatLng q) => _rad(q.latitude) * earthRadiusM;

    final ax = x(a), ay = y(a), bx = x(b), by = y(b), px = x(p), py = y(p);
    final dx = bx - ax, dy = by - ay;
    final len2 = dx * dx + dy * dy;
    double t = 0.0;
    if (len2 > 0) {
      t = ((px - ax) * dx + (py - ay) * dy) / len2;
      t = t.clamp(0.0, 1.0);
    }
    final cx = ax + t * dx, cy = ay + t * dy;
    return math.sqrt((px - cx) * (px - cx) + (py - cy) * (py - cy));
  }

  /// Distance in metres from [p] to the nearest point of [polyline], and the
  /// index of the segment start where that nearest point lies.
  static ({double distanceM, int segmentIndex}) distanceToPolyline(
    LatLng p,
    List<LatLng> polyline,
  ) {
    if (polyline.isEmpty) return (distanceM: double.infinity, segmentIndex: -1);
    if (polyline.length == 1) {
      return (distanceM: distanceM(p, polyline.first), segmentIndex: 0);
    }
    var best = double.infinity;
    var bestIdx = 0;
    for (var i = 0; i < polyline.length - 1; i++) {
      final d = distanceToSegmentM(p, polyline[i], polyline[i + 1]);
      if (d < best) {
        best = d;
        bestIdx = i;
      }
    }
    return (distanceM: best, segmentIndex: bestIdx);
  }

  /// Round metres to something speakable: 5 m steps under 50, 10 m under 200,
  /// 50 m under 1000, otherwise 100 m.
  static int roundForSpeech(double metres) {
    if (metres < 50) return (metres / 5).round() * 5;
    if (metres < 200) return (metres / 10).round() * 10;
    if (metres < 1000) return (metres / 50).round() * 50;
    return (metres / 100).round() * 100;
  }

  /// "350 metres" / "1.2 kilometres" for speech.
  static String speakDistance(double metres) {
    if (metres >= 1000) {
      final km = metres / 1000.0;
      final text = km >= 10 ? km.round().toString() : km.toStringAsFixed(1);
      return '$text kilometres';
    }
    final r = roundForSpeech(metres);
    if (r <= 0) return 'a few metres';
    return r == 1 ? '1 metre' : '$r metres';
  }

  /// "about 5 minutes" for speech.
  static String speakDuration(double seconds) {
    final mins = (seconds / 60.0).round();
    if (mins <= 1) return 'about 1 minute';
    if (mins < 60) return 'about $mins minutes';
    final h = mins ~/ 60;
    final m = mins % 60;
    return m == 0 ? 'about $h hours' : 'about $h hours $m minutes';
  }
}

import 'package:visionnav_app/services/navigation/geo_utils.dart';

/// Where the bus approach lies relative to the phone's current facing.
enum ApproachRelative {
  ahead,
  aheadLeft,
  left,
  behindLeft,
  behind,
  behindRight,
  right,
  aheadRight,
}

/// Orientation coach: face the bus **approach** direction so the vehicle
/// arrives in front of the camera, not from behind.
///
/// [approachBearingDeg] = travel bearing + 180° (where the bus comes from).
class ApproachFacingCoach {
  const ApproachFacingCoach();

  /// Normalize angle difference into (-180, 180].
  static double deltaDeg(double approachBearingDeg, double headingDeg) {
    var d = (approachBearingDeg - headingDeg) % 360;
    if (d > 180) d -= 360;
    if (d <= -180) d += 360;
    return d;
  }

  static ApproachRelative classify(
    double approachBearingDeg,
    double headingDeg, {
    double aheadToleranceDeg = 25,
  }) {
    final d = deltaDeg(approachBearingDeg, headingDeg);
    final abs = d.abs();
    if (abs <= aheadToleranceDeg) return ApproachRelative.ahead;
    if (abs >= 180 - aheadToleranceDeg) return ApproachRelative.behind;
    if (d > 0) {
      // Approach is clockwise from heading → turn right.
      if (d < 60) return ApproachRelative.aheadRight;
      if (d < 120) return ApproachRelative.right;
      return ApproachRelative.behindRight;
    }
    // Approach is counter-clockwise → turn left.
    if (abs < 60) return ApproachRelative.aheadLeft;
    if (abs < 120) return ApproachRelative.left;
    return ApproachRelative.behindLeft;
  }

  static bool isAligned(
    double approachBearingDeg,
    double headingDeg, {
    double aheadToleranceDeg = 25,
  }) =>
      classify(
        approachBearingDeg,
        headingDeg,
        aheadToleranceDeg: aheadToleranceDeg,
      ) ==
      ApproachRelative.ahead;

  /// Absolute fallback when the compass heading is unknown.
  static String absoluteSpeech({
    required double approachBearingDeg,
    required String toward,
  }) {
    final compass = GeoUtils.speakCompass(approachBearingDeg);
    return 'Face $compass. The bus toward $toward should come from $compass, '
        'so it arrives in front of the camera, not from behind. '
        'Say check direction after you turn. Compass accuracy can vary near metal.';
  }

  /// Relative turn coaching from current phone heading.
  static String relativeSpeech({
    required double approachBearingDeg,
    required double headingDeg,
    required String toward,
  }) {
    final relative = classify(approachBearingDeg, headingDeg);
    final compass = GeoUtils.speakCompass(approachBearingDeg);
    switch (relative) {
      case ApproachRelative.ahead:
        return 'Good. You are facing the approach for buses toward $toward. '
            'Keep the camera this way. The bus should come from ahead, about $compass.';
      case ApproachRelative.aheadLeft:
        return 'Turn a little left. The bus toward $toward approaches from slightly left of ahead, about $compass.';
      case ApproachRelative.aheadRight:
        return 'Turn a little right. The bus toward $toward approaches from slightly right of ahead, about $compass.';
      case ApproachRelative.left:
        return 'Turn left about 90 degrees. The bus toward $toward will come from your left, about $compass.';
      case ApproachRelative.right:
        return 'Turn right about 90 degrees. The bus toward $toward will come from your right, about $compass.';
      case ApproachRelative.behindLeft:
        return 'The bus toward $toward is mostly behind you, toward your left. '
            'Turn left and around so it approaches in front of the camera, about $compass.';
      case ApproachRelative.behindRight:
        return 'The bus toward $toward is mostly behind you, toward your right. '
            'Turn right and around so it approaches in front of the camera, about $compass.';
      case ApproachRelative.behind:
        return 'The bus toward $toward will come from behind you. '
            'Turn around about 180 degrees so it approaches in front of the camera, about $compass.';
    }
  }

  static String speech({
    required double approachBearingDeg,
    required String toward,
    double? headingDeg,
  }) {
    if (headingDeg == null) {
      return absoluteSpeech(
        approachBearingDeg: approachBearingDeg,
        toward: toward,
      );
    }
    return relativeSpeech(
      approachBearingDeg: approachBearingDeg,
      headingDeg: headingDeg,
      toward: toward,
    );
  }
}

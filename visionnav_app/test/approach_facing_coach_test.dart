import 'package:flutter_test/flutter_test.dart';
import 'package:visionnav_app/services/navigation/approach_facing_coach.dart';

void main() {
  test('classifies ahead, behind, left, and right from heading delta', () {
    expect(
      ApproachFacingCoach.classify(0, 0),
      ApproachRelative.ahead,
    );
    expect(
      ApproachFacingCoach.classify(0, 180),
      ApproachRelative.behind,
    );
    expect(
      ApproachFacingCoach.classify(0, 270),
      ApproachRelative.right,
    );
    expect(
      ApproachFacingCoach.classify(0, 90),
      ApproachRelative.left,
    );
  });

  test('behind speech tells the user to turn around for the camera', () {
    final speech = ApproachFacingCoach.relativeSpeech(
      approachBearingDeg: 0,
      headingDeg: 180,
      toward: 'PIMS',
    );
    expect(speech, contains('behind you'));
    expect(speech, contains('180'));
    expect(speech, contains('front of the camera'));
  });

  test('absolute speech used when heading is missing', () {
    final speech = ApproachFacingCoach.speech(
      approachBearingDeg: 90,
      toward: 'G-10 Markaz',
    );
    expect(speech, contains('Face east'));
    expect(speech, contains('check direction'));
  });

  test('aligned facing reports good', () {
    final speech = ApproachFacingCoach.speech(
      approachBearingDeg: 45,
      toward: 'Faizabad',
      headingDeg: 40,
    );
    expect(speech.startsWith('Good.'), isTrue);
    expect(ApproachFacingCoach.isAligned(45, 40), isTrue);
  });
}

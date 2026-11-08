import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/screens/destination_trip_screen.dart';
import 'package:visionnav_app/services/voice_commands.dart';

void main() {
  for (final action in ['yes', 'no', 'walk to mapped stop']) {
    final boarding = action == 'walk to mapped stop';
    testWidgets('spoken $action returns the appropriate trip outcome', (
      tester,
    ) async {
      TripWalk? result;
      var closed = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) {
              return Scaffold(
                body: TextButton(
                  onPressed: () async {
                    result = await Navigator.of(context).push<TripWalk>(
                      MaterialPageRoute(
                        builder: (_) => DestinationTripScreen(
                          now: () =>
                              DateTime.utc(2026, 11, 8, boarding ? 7 : 18, 15),
                          locate: () async =>
                              const LatLng(33.676728, 73.014472),
                        ),
                      ),
                    );
                    closed = true;
                  },
                  child: const Text('Open planner'),
                ),
              );
            },
          ),
        ),
      );
      await tester.tap(find.text('Open planner'));
      await tester.pumpAndSettle();
      final planned = await tester.runAsync(
        () => VoiceCommands.shared.dispatch('Karachi Company'),
      );
      expect(planned, isTrue);
      await tester.pumpAndSettle();
      expect(
        find.textContaining(
          boarding
              ? 'scheduled wait is about'
              : 'No more departures are listed',
        ),
        findsOneWidget,
      );
      expect(
        find.text(boarding ? 'Walk to mapped stop' : 'Yes, walk'),
        findsOneWidget,
      );
      final response = await tester.runAsync(
        () => VoiceCommands.shared.dispatch(action),
      );
      await tester.pumpAndSettle();
      expect(response, isTrue);
      expect(closed, isTrue);
      expect(
        result?.destination.name,
        boarding
            ? 'G-10 Markaz'
            : action == 'yes'
            ? 'Karachi Company'
            : null,
      );
      expect(
        result?.busPlan?.scannerTrip.direction,
        boarding ? 'fr_7_toward_pims' : null,
      );
    });
  }
}

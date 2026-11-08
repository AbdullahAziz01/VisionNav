import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:visionnav_app/screens/destination_trip_screen.dart';
import 'package:visionnav_app/services/navigation/route_models.dart';
import 'package:visionnav_app/services/voice_commands.dart';

void main() {
  for (final accepted in [true, false]) {
    testWidgets(
      'spoken ${accepted ? 'yes starts walking handoff' : 'no cancels'} after last bus',
      (tester) async {
        Place? result;
        var closed = false;
        await tester.pumpWidget(
          MaterialApp(
            home: Builder(
              builder: (context) {
                return Scaffold(
                  body: TextButton(
                    onPressed: () async {
                      result = await Navigator.of(context).push<Place>(
                        MaterialPageRoute(
                          builder: (_) => DestinationTripScreen(
                            now: () => DateTime.utc(2026, 11, 8, 18, 15),
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
          find.textContaining('No more departures are listed'),
          findsOneWidget,
        );
        expect(find.text('Yes, walk'), findsOneWidget);
        final response = await tester.runAsync(
          () => VoiceCommands.shared.dispatch(accepted ? 'yes' : 'no'),
        );
        await tester.pumpAndSettle();
        expect(response, isTrue);
        expect(closed, isTrue);
        expect(result?.name, accepted ? 'Karachi Company' : null);
      },
    );
  }
}

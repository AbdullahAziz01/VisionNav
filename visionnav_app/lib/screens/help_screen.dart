import 'package:flutter/material.dart';
import 'package:visionnav_app/core/theme.dart';

class HelpScreen extends StatelessWidget {
  const HelpScreen({super.key});

  @override
  Widget build(BuildContext context) {
    const steps = [
      (
        'Say your destination',
        'From Home, choose Plan a bus trip. Say or type a supported destination, such as Karachi Company.',
      ),
      (
        'Review the proposed trip',
        'The planner proposes a boarding stop, direction, and exit stop. Confirm the boarding point and service. The manual route option can start walking directions to a stand you know.',
      ),
      (
        'Scan the bus sign',
        'At the stop, point the rear camera at the bus sign. The scanner speaks when it finds your route and direction.',
      ),
      (
        'Confirm before boarding',
        'Confirm the destination with the driver before boarding.',
      ),
    ];
    return Scaffold(
      appBar: AppBar(title: const Text('Help & About')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 28),
        children: [
          const Card(
            child: Padding(
              padding: EdgeInsets.all(20),
              child: Text(
                'Voice controls: say add location, open camera, plan a bus trip, or open settings. Say voice help for app commands and screen commands for the current screen. Use Pause voice and Resume voice to control listening.',
              ),
            ),
          ),
          const SizedBox(height: 20),
          Text(
            'A little guidance\nfor your journey.',
            style: Theme.of(context).textTheme.headlineMedium,
          ),
          const SizedBox(height: 12),
          const Text('Walk to a stop and identify your bus'),
          const SizedBox(height: 24),
          for (var i = 0; i < steps.length; i++) ...[
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'STEP ${i + 1}',
                      style: const TextStyle(
                        color: AppTheme.accent,
                        fontSize: 12,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      steps[i].$1,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(steps[i].$2),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],
          const SizedBox(height: 8),
          const Text(
            'Settings lets you enter your walking-directions key and test the vision backend.',
          ),
        ],
      ),
    );
  }
}

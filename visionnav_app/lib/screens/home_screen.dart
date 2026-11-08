import 'package:flutter/material.dart';
import 'package:visionnav_app/core/theme.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key, this.onPlanBusTrip, this.onManualTrip});
  final VoidCallback? onPlanBusTrip;
  final VoidCallback? onManualTrip;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('VisionNav Home')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 28),
        children: [
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Color(0xFF203D4B), AppTheme.surface],
              ),
              borderRadius: BorderRadius.circular(28),
              border: Border.all(color: const Color(0xFF385764)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const ExcludeSemantics(
                  child: Icon(
                    Icons.explore_outlined,
                    size: 44,
                    color: AppTheme.accent,
                  ),
                ),
                const SizedBox(height: 24),
                Text(
                  'Your journey,\none step at a time.',
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
                const SizedBox(height: 12),
                const Text(
                  'Walking directions and bus identification, with spoken guidance.',
                ),
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: onPlanBusTrip,
                    icon: const Icon(Icons.directions_bus_outlined),
                    label: const Text('Plan a bus trip'),
                  ),
                ),
              ],
            ),
          ),
          if (onManualTrip != null)
            TextButton(
              onPressed: onManualTrip,
              child: const Text("Choose a bus route manually"),
            ),
          const SizedBox(height: 28),
          Text(
            'Your journey with VisionNav',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 16),
          const _JourneyStep(
            number: '01',
            icon: Icons.route_outlined,
            title: 'Say where you want to go',
            subtitle:
                'Get a suggested boarding stop, direction, and exit stop.',
          ),
          const SizedBox(height: 12),
          const _JourneyStep(
            number: '02',
            icon: Icons.directions_walk,
            title: 'Walk to the stand',
            subtitle: 'Follow spoken walking directions.',
          ),
          const SizedBox(height: 12),
          const _JourneyStep(
            number: '03',
            icon: Icons.document_scanner_outlined,
            title: 'Identify your bus',
            subtitle: 'Scan the sign to check your route.',
          ),
        ],
      ),
    );
  }
}

class _JourneyStep extends StatelessWidget {
  const _JourneyStep({
    required this.number,
    required this.icon,
    required this.title,
    required this.subtitle,
  });
  final String number;
  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ExcludeSemantics(child: Icon(icon, color: AppTheme.accent, size: 28)),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 4),
                Text(subtitle),
              ],
            ),
          ),
          const SizedBox(width: 8),
          ExcludeSemantics(
            child: Text(
              number,
              style: const TextStyle(color: AppTheme.accent, fontSize: 13),
            ),
          ),
        ],
      ),
    ),
  );
}

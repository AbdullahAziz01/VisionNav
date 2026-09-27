import 'package:flutter_test/flutter_test.dart';
import 'package:visionnav_app/services/navigation_service.dart';
import 'package:visionnav_app/services/service_interfaces.dart';

class _FakeLocation implements LocationService {
  _FakeLocation(this.granted);
  final bool granted;

  @override
  Future<bool> requestPermissions() async => granted;

  @override
  Stream<Map<String, double>> get locationStream => const Stream.empty();
}

void main() {
  test('startNavigation without a destination throws', () async {
    final nav = BasicNavigationService(_FakeLocation(true));
    expect(nav.startNavigation(), throwsStateError);
    expect(nav.status, NavigationStatus.idle);
  });

  test('start/stop transitions status and emits on the stream', () async {
    final nav = BasicNavigationService(_FakeLocation(true));
    final emitted = <NavigationStatus>[];
    nav.statusStream.listen(emitted.add);

    await nav.setDestination('Central Bus Stand');
    expect(nav.destination, 'Central Bus Stand');

    await nav.startNavigation();
    expect(nav.status, NavigationStatus.navigating);

    await nav.stopNavigation();
    expect(nav.status, NavigationStatus.idle);

    await Future<void>.delayed(Duration.zero);
    expect(emitted,
        [NavigationStatus.navigating, NavigationStatus.idle]);
    await nav.dispose();
  });

  test('startNavigation fails when location permission is unavailable', () async {
    final nav = BasicNavigationService(_FakeLocation(false));
    await nav.setDestination('Somewhere');
    expect(nav.startNavigation(), throwsStateError);
    expect(nav.status, NavigationStatus.idle);
  });
}

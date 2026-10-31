import 'package:flutter_test/flutter_test.dart';
import 'package:visionnav_app/services/capped_backoff.dart';

void main() {
  test('exponential retry delays stop increasing at the cap and reset', () {
    final backoff = CappedBackoff(
      initial: const Duration(seconds: 1),
      maximum: const Duration(seconds: 5),
    );

    expect(backoff.nextDelay(), const Duration(seconds: 1));
    expect(backoff.nextDelay(), const Duration(seconds: 2));
    expect(backoff.nextDelay(), const Duration(seconds: 4));
    expect(backoff.nextDelay(), const Duration(seconds: 5));
    expect(backoff.nextDelay(), const Duration(seconds: 5));

    backoff.reset();
    expect(backoff.nextDelay(), const Duration(seconds: 1));
  });
}

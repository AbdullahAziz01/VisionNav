/// Exponential retry delays capped at [maximum].
class CappedBackoff {
  CappedBackoff({
    this.initial = const Duration(seconds: 1),
    this.maximum = const Duration(seconds: 30),
  }) : assert(initial > Duration.zero),
       assert(maximum >= initial);

  final Duration initial;
  final Duration maximum;
  int _attempt = 0;

  Duration nextDelay() {
    var delayMs = initial.inMilliseconds;
    for (
      var index = 0;
      index < _attempt && delayMs < maximum.inMilliseconds;
      index++
    ) {
      delayMs = (delayMs * 2).clamp(0, maximum.inMilliseconds).toInt();
    }
    if (delayMs < maximum.inMilliseconds) _attempt++;
    return Duration(milliseconds: delayMs);
  }

  void reset() => _attempt = 0;
}

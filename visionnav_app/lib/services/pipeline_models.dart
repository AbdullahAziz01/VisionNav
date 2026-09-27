class TrackedDetection {
  const TrackedDetection({
    required this.trackId,
    required this.className,
    required this.confidence,
    required this.bboxXyxy,
    this.estimatedDistanceM,
    required this.distanceLabel,
    this.routeLine,
    this.routeDestination,
    this.routeDirection,
    this.routeConfidence,
    this.routeIsStable = false,
    this.routeTtsMessage,
  });

  final int trackId;
  final String className;
  final double confidence;
  final List<double> bboxXyxy;
  final double? estimatedDistanceM;
  final String distanceLabel;
  final String? routeLine;
  final String? routeDestination;
  final String? routeDirection;
  final double? routeConfidence;
  final bool routeIsStable;
  final String? routeTtsMessage;

  factory TrackedDetection.fromJson(Map<String, dynamic> json) {
    final bbox = (json['bbox_xyxy'] as List<dynamic>? ?? const [])
        .map((v) => (v as num).toDouble())
        .toList();
    return TrackedDetection(
      trackId: (json['track_id'] as num?)?.toInt() ?? -1,
      className: json['class'] as String? ?? 'object',
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      bboxXyxy: bbox,
      estimatedDistanceM: (json['estimated_distance_m'] as num?)?.toDouble(),
      distanceLabel: json['distance_label'] as String? ?? 'distance unavailable',
      routeLine: _jsonString(json['route_line']),
      routeDestination: _jsonString(json['route_destination']),
      routeDirection: _jsonString(json['route_direction']),
      routeConfidence: _jsonDouble(json['route_confidence']),
      routeIsStable: json['route_is_stable'] is bool
          ? json['route_is_stable'] as bool
          : false,
      routeTtsMessage: _jsonString(json['route_tts_message']),
    );
  }
}

String? _jsonString(dynamic value) => value is String ? value : null;

double? _jsonDouble(dynamic value) => value is num ? value.toDouble() : null;

class PipelineFrameResult {
  const PipelineFrameResult({
    required this.frameIndex,
    required this.mode,
    required this.objects,
    this.depthBackend,
    this.frameWidthPx,
    this.frameHeightPx,
  });

  final int frameIndex;
  final String mode;
  final String? depthBackend;
  final List<TrackedDetection> objects;

  /// Size of the frame the server actually ran detection on (after EXIF
  /// rotation). Bounding boxes are in this coordinate space, so the overlay
  /// must scale from these dimensions, not from the raw JPEG header.
  final int? frameWidthPx;
  final int? frameHeightPx;

  factory PipelineFrameResult.fromJson(Map<String, dynamic> json) {
    final raw = json['objects'] as List<dynamic>? ?? const [];
    final debug = json['debug'] as Map<String, dynamic>? ?? const {};
    return PipelineFrameResult(
      frameIndex: (json['frame_index'] as num?)?.toInt() ?? 0,
      mode: json['mode'] as String? ?? 'monocular',
      depthBackend: json['depth_backend'] as String?,
      frameWidthPx: (debug['frame_width_px'] as num?)?.toInt(),
      frameHeightPx: (debug['frame_height_px'] as num?)?.toInt(),
      objects: raw
          .whereType<Map<String, dynamic>>()
          .map(TrackedDetection.fromJson)
          .toList(),
    );
  }
}

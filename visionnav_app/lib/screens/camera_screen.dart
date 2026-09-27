import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:visionnav_app/services/announcement_manager.dart';
import 'package:visionnav_app/services/camera_service.dart';
import 'package:visionnav_app/services/pipeline_models.dart';
import 'package:visionnav_app/services/tts_service.dart';
import 'package:visionnav_app/services/visionnav_api.dart';

class CameraScreen extends StatefulWidget {
  const CameraScreen({super.key});

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> with WidgetsBindingObserver {
  late final CameraService _cameraService;
  late final HttpVisionNavApi _api;
  late final FlutterTtsService _tts;
  final AnnouncementManager _announcer = AnnouncementManager();
  StreamSubscription<Map<String, dynamic>>? _resultSub;
  Timer? _captureTimer;

  bool _isInitializing = true;
  bool _requestInFlight = false;
  String? _errorMsg;
  String? _apiStatus;
  bool _permissionPermanentlyDenied = false;
  bool _ttsEnabled = true;
  String? _lastSpoken;
  PipelineFrameResult? _latestResult;
  Size? _frameSize;

  static const Duration _captureInterval = Duration(milliseconds: 500);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _cameraService = CameraService();
    _api = HttpVisionNavApi();
    _tts = FlutterTtsService.shared;
    unawaited(_tts.initialize());
    _initCamera();
  }

  /// Runs on every pipeline result; speaks at most one short phrase and never
  /// awaits the engine, so the preview and upload loop are unaffected.
  void _announce(PipelineFrameResult result) {
    final phrase = _announcer.next(
      result.objects,
      canSpeak: _ttsEnabled && !_tts.isSpeaking,
    );
    if (phrase == null) return;
    _lastSpoken = phrase;
    unawaited(_tts.speak(phrase));
  }

  void _toggleTts() {
    setState(() => _ttsEnabled = !_ttsEnabled);
    if (!_ttsEnabled) unawaited(_tts.stop());
  }

  Future<void> _initCamera() async {
    if (!mounted) return;

    _stopPipelineLoop();
    setState(() {
      _isInitializing = true;
      _errorMsg = null;
      _apiStatus = null;
      _permissionPermanentlyDenied = false;
    });

    try {
      await _cameraService.initialize();
      if (mounted) {
        setState(() {
          _isInitializing = false;
        });
      }
      await _startPipelineLoop();
    } on CameraPermissionException catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMsg = e.message;
        _permissionPermanentlyDenied = e.message.contains('permanently denied');
        _isInitializing = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMsg = 'Failed to initialize camera: $e';
        _isInitializing = false;
      });
    }
  }

  Future<void> _startPipelineLoop() async {
    await _resultSub?.cancel();
    _resultSub = _api.resultsStream.listen((map) {
      if (!mounted) return;
      final result = PipelineFrameResult.fromJson(map);
      setState(() {
        _latestResult = result;
        // Boxes are in the server's (EXIF-rotated) frame space; use its size.
        if (result.frameWidthPx != null && result.frameHeightPx != null) {
          _frameSize = Size(
            result.frameWidthPx!.toDouble(),
            result.frameHeightPx!.toDouble(),
          );
        }
        _apiStatus = 'Connected · ${result.objects.length} objects';
      });
      _announce(result);
    });

    try {
      await _api.connect();
      if (mounted) {
        setState(() {
          _apiStatus = 'Connected to $kVisionNavApiBaseUrl';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _apiStatus =
              'API offline. Start FastAPI on PC and set kVisionNavApiBaseUrl.\n$e';
        });
      }
      return;
    }

    _captureTimer?.cancel();
    _captureTimer = Timer.periodic(_captureInterval, (_) {
      unawaited(_captureAndSend());
    });
  }

  Future<void> _captureAndSend() async {
    if (_requestInFlight || !_api.isConnected) return;
    final controller = _cameraService.controller;
    if (controller == null || !controller.value.isInitialized) return;

    _requestInFlight = true;
    try {
      final bytes = await _cameraService.captureJpeg();
      await _api.sendFrame(bytes);
    } catch (e) {
      if (mounted) {
        setState(() {
          _apiStatus = 'Frame send failed: $e';
        });
      }
    } finally {
      _requestInFlight = false;
    }
  }

  void _stopPipelineLoop() {
    _captureTimer?.cancel();
    _captureTimer = null;
    _requestInFlight = false;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _stopPipelineLoop();
    _resultSub?.cancel();
    _api.dispose();
    // Shared engine: stop our announcements but keep it alive for navigation.
    unawaited(_tts.stop());
    _cameraService.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final controller = _cameraService.controller;
    if (controller == null || !controller.value.isInitialized) {
      return;
    }

    if (state == AppLifecycleState.inactive || state == AppLifecycleState.paused) {
      _stopPipelineLoop();
      unawaited(_tts.stop());
      _cameraService.dispose();
    } else if (state == AppLifecycleState.resumed) {
      _announcer.reset();
      _initCamera();
    }
  }

  Widget _buildPreview(CameraController controller) {
    final previewSize = controller.value.previewSize;
    if (previewSize == null) {
      return const Center(child: CircularProgressIndicator(color: Colors.tealAccent));
    }

    return ClipRect(
      child: OverflowBox(
        alignment: Alignment.center,
        child: FittedBox(
          fit: BoxFit.cover,
          child: SizedBox(
            width: previewSize.height,
            height: previewSize.width,
            child: CameraPreview(controller),
          ),
        ),
      ),
    );
  }

  Widget _buildErrorBody() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.videocam_off, size: 64, color: Colors.redAccent),
            const SizedBox(height: 16),
            Text(
              _errorMsg ?? 'Camera not available.',
              style: const TextStyle(color: Colors.redAccent, fontSize: 18),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: _initCamera,
              child: const Text('Retry'),
            ),
            if (_permissionPermanentlyDenied) ...[
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: openAppSettings,
                child: const Text('Open Settings'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildStatusBar() {
    final objects = _latestResult?.objects ?? const <TrackedDetection>[];
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: Colors.black54,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            _apiStatus ?? 'Connecting to pipeline...',
            style: const TextStyle(color: Colors.white70, fontSize: 13),
            textAlign: TextAlign.center,
          ),
          if (_lastSpoken != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                _ttsEnabled ? '🔊 $_lastSpoken' : '🔇 Voice muted',
                style: const TextStyle(color: Colors.tealAccent, fontSize: 13),
                textAlign: TextAlign.center,
              ),
            ),
          if (objects.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text(
                'No objects detected.',
                style: TextStyle(color: Colors.white, fontSize: 16),
              ),
            )
          else
            ...objects.take(4).map(
              (obj) => Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  '${obj.className} ID ${obj.trackId}  ${(obj.confidence * 100).round()}%  ·  ${obj.distanceLabel}',
                  style: const TextStyle(color: Colors.white, fontSize: 15),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_isInitializing) {
      return Scaffold(
        appBar: AppBar(title: const Text('Live Vision')),
        body: const Center(
          child: CircularProgressIndicator(color: Colors.tealAccent),
        ),
      );
    }

    final controller = _cameraService.controller;
    if (_errorMsg != null || controller == null || !controller.value.isInitialized) {
      return Scaffold(
        appBar: AppBar(title: const Text('Live Vision')),
        body: _buildErrorBody(),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Live Vision'),
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          IconButton(
            tooltip: _ttsEnabled ? 'Mute voice' : 'Unmute voice',
            icon: Icon(_ttsEnabled ? Icons.volume_up : Icons.volume_off),
            onPressed: _toggleTts,
          ),
        ],
      ),
      extendBodyBehindAppBar: true,
      body: Stack(
        fit: StackFit.expand,
        children: [
          _buildPreview(controller),
          if (_latestResult != null)
            Positioned.fill(
              child: CustomPaint(
                painter: _DetectionPainter(
                  objects: _latestResult!.objects,
                  imageSize: _frameSize ??
                      Size(
                        controller.value.previewSize?.height ?? 1,
                        controller.value.previewSize?.width ?? 1,
                      ),
                ),
              ),
            ),
          Positioned(
            bottom: 16,
            left: 0,
            right: 0,
            child: _buildStatusBar(),
          ),
        ],
      ),
    );
  }
}

class _DetectionPainter extends CustomPainter {
  _DetectionPainter({required this.objects, required this.imageSize});

  final List<TrackedDetection> objects;
  final Size imageSize;

  @override
  void paint(Canvas canvas, Size size) {
    if (imageSize.width <= 0 || imageSize.height <= 0) return;

    final scaleX = size.width / imageSize.width;
    final scaleY = size.height / imageSize.height;
    final used = scaleX > scaleY ? scaleX : scaleY;
    final dx = (size.width - imageSize.width * used) / 2;
    final dy = (size.height - imageSize.height * used) / 2;

    final boxPaint = Paint()
      ..color = Colors.tealAccent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    final textPainter = TextPainter(textDirection: TextDirection.ltr);

    for (final obj in objects) {
      if (obj.bboxXyxy.length < 4) continue;
      final rect = Rect.fromLTRB(
        dx + obj.bboxXyxy[0] * used,
        dy + obj.bboxXyxy[1] * used,
        dx + obj.bboxXyxy[2] * used,
        dy + obj.bboxXyxy[3] * used,
      );
      canvas.drawRect(rect, boxPaint);

      final label =
          '${obj.className} #${obj.trackId}  ${obj.estimatedDistanceM?.toStringAsFixed(1) ?? '--'} m';
      textPainter.text = TextSpan(
        text: label,
        style: const TextStyle(
          color: Colors.black,
          backgroundColor: Colors.tealAccent,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      );
      textPainter.layout();
      textPainter.paint(canvas, Offset(rect.left, (rect.top - 16).clamp(0, size.height)));
    }
  }

  @override
  bool shouldRepaint(covariant _DetectionPainter oldDelegate) {
    return oldDelegate.objects != objects || oldDelegate.imageSize != imageSize;
  }
}

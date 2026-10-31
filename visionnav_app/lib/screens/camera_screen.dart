import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:visionnav_app/services/announcement_manager.dart';
import 'package:visionnav_app/services/capped_backoff.dart';
import 'package:visionnav_app/services/camera_service.dart';
import 'package:visionnav_app/services/pipeline_models.dart';
import 'package:visionnav_app/services/tts_service.dart';
import 'package:visionnav_app/services/visionnav_api.dart';

class CameraScreen extends StatefulWidget {
  const CameraScreen({super.key});

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen>
    with WidgetsBindingObserver {
  late final CameraService _cameraService;
  late final HttpVisionNavApi _api;
  late final FlutterTtsService _tts;
  final AnnouncementManager _announcer = AnnouncementManager();
  StreamSubscription<Map<String, dynamic>>? _resultSub;
  Timer? _captureTimer;
  Timer? _reconnectTimer;
  final CappedBackoff _reconnectBackoff = CappedBackoff();
  Future<void>? _pipelineStartFuture;
  Future<void> _pendingLifecycleRelease = Future<void>.value();
  int _session = 0;
  int _lifecycleEpoch = 0;
  bool _screenDisposed = false;
  bool _lifecyclePaused = false;
  bool _resumeWaitingForRelease = false;

  bool _isInitializing = true;
  int? _requestInFlightSession;
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

  bool _isCurrentSession(int session) =>
      !_screenDisposed && !_lifecyclePaused && session == _session && mounted;

  Future<void> _initCamera() async {
    final session = ++_session;
    _stopPipelineLoop();
    _reconnectBackoff.reset();
    if (_screenDisposed) return;

    if (mounted) {
      setState(() {
        _isInitializing = true;
        _errorMsg = null;
        _apiStatus = null;
        _permissionPermanentlyDenied = false;
      });
    }

    try {
      await _cameraService.initialize();
      if (!_isCurrentSession(session)) return;
      setState(() {
        _isInitializing = false;
      });
      await _startAndTrackPipeline(session);
    } on CameraPermissionException catch (e) {
      if (!_isCurrentSession(session)) return;
      setState(() {
        _errorMsg = e.message;
        _permissionPermanentlyDenied = e.message.contains('permanently denied');
        _isInitializing = false;
      });
    } catch (e) {
      if (!_isCurrentSession(session)) return;
      setState(() {
        _errorMsg = 'Failed to initialize camera: $e';
        _isInitializing = false;
      });
    }
  }

  Future<void> _startPipelineLoop(int session) async {
    if (!_isCurrentSession(session)) return;

    await _resultSub?.cancel();
    if (!_isCurrentSession(session)) return;
    _resultSub = _api.resultsStream.listen((map) {
      if (!_isCurrentSession(session)) return;
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
      if (!_isCurrentSession(session)) return;
      await _api.acquireSession();

      if (!_isCurrentSession(session)) return;
      setState(() {
        _apiStatus = 'Connected to ${_api.baseUrl}';
      });
    } on BackendNetworkException catch (e) {
      _scheduleReconnect(session, e);
      return;
    } on SessionConflictException catch (e) {
      if (!_isCurrentSession(session)) return;
      _stopCaptureTimer();
      setState(() {
        _apiStatus = 'Session Conflict: $e\nOpen Settings to force take over.';
      });
      return;
    } on BackendAuthException {
      if (!_isCurrentSession(session)) return;
      _stopCaptureTimer();
      setState(() {
        _apiStatus = 'Authentication Failed: Invalid API Key.\nCheck Settings.';
      });
      return;
    } on BackendUnavailableException catch (e) {
      if (!_isCurrentSession(session)) return;
      _stopCaptureTimer();
      setState(() => _apiStatus = 'Backend not ready: $e');
      return;
    } on PayloadTooLargeException catch (e) {
      if (!_isCurrentSession(session)) return;
      _stopCaptureTimer();
      setState(() => _apiStatus = 'Upload Limit Exceeded: $e');
      return;
    } on BackendHttpException catch (e) {
      if (!_isCurrentSession(session)) return;
      _stopCaptureTimer();
      setState(() => _apiStatus = 'Backend error: $e');
      return;
    } catch (e) {
      if (!_isCurrentSession(session)) return;
      setState(() {
        _apiStatus = 'API offline (${_api.baseUrl}).\n$e';
      });
      return;
    }

    if (!_isCurrentSession(session)) return;
    _captureTimer?.cancel();
    _captureTimer = Timer.periodic(_captureInterval, (_) {
      if (!_isCurrentSession(session)) return;
      unawaited(_captureAndSend(session));
    });
  }

  Future<void> _startAndTrackPipeline(int session) async {
    final startFuture = _startPipelineLoop(session);
    _pipelineStartFuture = startFuture;
    try {
      await startFuture;
    } finally {
      if (identical(_pipelineStartFuture, startFuture)) {
        _pipelineStartFuture = null;
      }
    }
  }

  Future<void> _captureAndSend(int session) async {
    if (!_isCurrentSession(session) ||
        _requestInFlightSession != null ||
        !_api.isConnected) {
      return;
    }
    if (!_cameraService.isInitialized) return;

    _requestInFlightSession = session;
    try {
      final bytes = await _cameraService.captureJpeg();
      if (!_isCurrentSession(session)) return;
      await _api.sendFrame(bytes);
      _reconnectBackoff.reset();
    } on SessionConflictException catch (e) {
      if (!_isCurrentSession(session)) return;
      _stopCaptureTimer();
      setState(() {
        _apiStatus = 'Session Conflict: $e\nOpen Settings to acquire session.';
      });
    } on BackendAuthException catch (e) {
      if (!_isCurrentSession(session)) return;
      _stopCaptureTimer();
      setState(() {
        _apiStatus = 'Auth Failed: $e\nCheck Settings.';
      });
    } on PayloadTooLargeException catch (e) {
      if (!_isCurrentSession(session)) return;
      _stopCaptureTimer();
      setState(() {
        _apiStatus = 'Upload Limit Exceeded: $e';
      });
    } on BackendUnavailableException catch (e) {
      if (!_isCurrentSession(session)) return;
      _stopCaptureTimer();
      setState(() => _apiStatus = 'Backend not ready: $e');
    } on BackendHttpException catch (e) {
      if (!_isCurrentSession(session)) return;
      _stopCaptureTimer();
      setState(() => _apiStatus = 'Backend error: $e');
    } on BackendNetworkException catch (e) {
      _scheduleReconnect(session, e);
    } catch (e) {
      if (!_isCurrentSession(session)) return;
      setState(() {
        _apiStatus = 'Frame send failed: $e';
      });
    } finally {
      if (_requestInFlightSession == session) {
        _requestInFlightSession = null;
      }
    }
  }

  void _scheduleReconnect(int session, Object error) {
    if (!_isCurrentSession(session) || _reconnectTimer != null) return;
    _stopCaptureTimer();
    final delay = _reconnectBackoff.nextDelay();
    setState(() {
      _apiStatus =
          'Network unavailable ($error). Retrying in ${delay.inSeconds}s.';
    });
    _reconnectTimer = Timer(delay, () {
      _reconnectTimer = null;
      if (_isCurrentSession(session)) {
        unawaited(_startAndTrackPipeline(session));
      }
    });
  }

  void _stopCaptureTimer() {
    _captureTimer?.cancel();
    _captureTimer = null;
  }

  void _stopPipelineLoop() {
    _stopCaptureTimer();
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
  }

  Future<void> _releaseCameraForLifecycle() {
    if (_lifecyclePaused) {
      if (_resumeWaitingForRelease) {
        _lifecycleEpoch++;
        _resumeWaitingForRelease = false;
      }
      return _pendingLifecycleRelease;
    }
    _lifecyclePaused = true;
    final lifecycleEpoch = ++_lifecycleEpoch;
    final releasedSessionId = _api.config.sessionId;
    _session++;
    _stopPipelineLoop();
    _api.invalidatePendingOperations();
    unawaited(_tts.stop());
    if (mounted) {
      setState(() {
        _isInitializing = true;
        _errorMsg = null;
      });
    }

    final pendingStart = _pipelineStartFuture;
    final release = () async {
      if (pendingStart != null) {
        try {
          await pendingStart;
        } catch (_) {
          // Startup failure must not prevent the matching session release.
        }
      }
      if (_screenDisposed || lifecycleEpoch != _lifecycleEpoch) return;
      try {
        await _api.releaseSession(sessionId: releasedSessionId);
      } catch (_) {
        // Release is best-effort; the server lease will expire if offline.
      }
    }();
    final cameraRelease = _cameraService.dispose().catchError((Object _) {});
    _pendingLifecycleRelease = Future.wait<void>([release, cameraRelease]);
    return _pendingLifecycleRelease;
  }

  Future<void> _resumeAfterLifecycle() async {
    if (!_lifecyclePaused || _resumeWaitingForRelease) return;
    final lifecycleEpoch = _lifecycleEpoch;
    _resumeWaitingForRelease = true;
    await _pendingLifecycleRelease;
    _resumeWaitingForRelease = false;
    if (_screenDisposed ||
        !mounted ||
        !_lifecyclePaused ||
        lifecycleEpoch != _lifecycleEpoch) {
      return;
    }
    // A new session ID ensures a late pause-release can never release the
    // resumed session. If the old lease remains, the server returns 409.
    _api.config.resetSessionId();
    _lifecyclePaused = false;
    _announcer.reset();
    await _initCamera();
  }

  @override
  void dispose() {
    _screenDisposed = true;
    _lifecyclePaused = true;
    _lifecycleEpoch++;
    WidgetsBinding.instance.removeObserver(this);
    _session++;
    _stopPipelineLoop();
    final releasedSessionId = _api.config.sessionId;
    _api.invalidatePendingOperations();
    _resultSub?.cancel();
    unawaited(
      _api
          .releaseSession(sessionId: releasedSessionId)
          .catchError((Object _) {})
          .whenComplete(_api.dispose),
    );
    // Shared engine: stop our announcements but keep it alive for navigation.
    unawaited(_tts.stop());
    unawaited(_cameraService.dispose());
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_screenDisposed) return;

    switch (state) {
      case AppLifecycleState.inactive:
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
        unawaited(_releaseCameraForLifecycle());
        break;
      case AppLifecycleState.resumed:
        unawaited(_resumeAfterLifecycle());
        break;
      case AppLifecycleState.detached:
        unawaited(_releaseCameraForLifecycle());
        break;
    }
  }

  Widget _buildPreview(CameraController controller) {
    final previewSize = controller.value.previewSize;
    if (previewSize == null) {
      return const Center(
        child: CircularProgressIndicator(color: Colors.tealAccent),
      );
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
            ElevatedButton(onPressed: _initCamera, child: const Text('Retry')),
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
            ...objects
                .take(4)
                .map(
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
    if (_errorMsg != null ||
        controller == null ||
        !controller.value.isInitialized) {
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
                  imageSize:
                      _frameSize ??
                      Size(
                        controller.value.previewSize?.height ?? 1,
                        controller.value.previewSize?.width ?? 1,
                      ),
                ),
              ),
            ),
          Positioned(bottom: 16, left: 0, right: 0, child: _buildStatusBar()),
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
      textPainter.paint(
        canvas,
        Offset(rect.left, (rect.top - 16).clamp(0, size.height)),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _DetectionPainter oldDelegate) {
    return oldDelegate.objects != objects || oldDelegate.imageSize != imageSize;
  }
}

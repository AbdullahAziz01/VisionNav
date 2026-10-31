import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:permission_handler/permission_handler.dart';

class CameraPermissionException implements Exception {
  CameraPermissionException(this.message);
  final String message;

  @override
  String toString() => message;
}

class CameraService {
  CameraController? _controller;
  List<CameraDescription> _cameras = [];
  bool _isInitialized = false;
  int _epoch = 0;
  Future<void> _chain = Future.value();

  CameraController? get controller => _controller;
  bool get isInitialized =>
      _isInitialized && _controller != null && _controller!.value.isInitialized;

  Future<void> initialize() {
    _chain = _chain.catchError((_) {}).then((_) => _initialize());
    return _chain;
  }

  Future<void> _initialize() async {
    if (isInitialized) return;

    final epoch = ++_epoch;

    final permission = await Permission.camera.request();
    if (epoch != _epoch) return;
    if (!permission.isGranted) {
      if (permission.isPermanentlyDenied) {
        throw CameraPermissionException(
          'Camera permission permanently denied. Enable it in Android Settings > Apps > VisionNav > Permissions.',
        );
      }
      throw CameraPermissionException('Camera permission denied.');
    }

    _cameras = await availableCameras();
    if (epoch != _epoch) return;
    if (_cameras.isEmpty) {
      throw CameraPermissionException('No cameras found on this device.');
    }

    final selectedCamera = _selectRearCamera(_cameras);
    final previous = _controller;
    _controller = null;
    _isInitialized = false;
    await previous?.dispose();
    if (epoch != _epoch) return;

    final next = CameraController(
      selectedCamera,
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.yuv420,
    );

    try {
      await next.initialize();
      if (epoch != _epoch) {
        await next.dispose();
        return;
      }
      _controller = next;
      _isInitialized = true;
      debugPrint(
        'Camera initialized: ${selectedCamera.name} (${selectedCamera.lensDirection})',
      );
    } catch (e) {
      await next.dispose();
      if (epoch == _epoch) {
        _controller = null;
        _isInitialized = false;
      }
      debugPrint('Error initializing camera: $e');
      rethrow;
    }
  }

  CameraDescription _selectRearCamera(List<CameraDescription> cameras) {
    for (final camera in cameras) {
      if (camera.lensDirection == CameraLensDirection.back) {
        return camera;
      }
    }
    return cameras.first;
  }

  Future<List<int>> captureJpeg() async {
    final controller = _controller;
    if (!_isInitialized || controller == null || !controller.value.isInitialized) {
      throw StateError('Camera is not initialized.');
    }
    if (controller.value.isTakingPicture) {
      throw StateError('Capture already in progress.');
    }
    final file = await controller.takePicture();
    if (_controller != controller || !controller.value.isInitialized) {
      throw StateError('Camera was released during capture.');
    }
    return file.readAsBytes();
  }

  /// Placeholder for Phase 3: Start streaming frames to the backend
  void startFrameStreaming(void Function(CameraImage) onFrameAvailable) {
    if (!_isInitialized || _controller == null) return;
    if (_controller!.value.isStreamingImages) return;

    _controller!.startImageStream(onFrameAvailable);
  }

  void stopFrameStreaming() {
    if (_controller != null && _controller!.value.isStreamingImages) {
      _controller!.stopImageStream();
    }
  }

  Future<void> dispose() {
    _chain = _chain.catchError((_) {}).then((_) => _dispose());
    return _chain;
  }

  Future<void> _dispose() async {
    _epoch++;
    stopFrameStreaming();
    final controller = _controller;
    _controller = null;
    _isInitialized = false;
    if (controller != null) {
      await controller.dispose();
    }
  }
}

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

  CameraController? get controller => _controller;
  bool get isInitialized => _isInitialized;

  Future<void> initialize() async {
    if (_isInitialized && _controller != null && _controller!.value.isInitialized) {
      return;
    }

    final permission = await Permission.camera.request();
    if (!permission.isGranted) {
      if (permission.isPermanentlyDenied) {
        throw CameraPermissionException(
          'Camera permission permanently denied. Enable it in Android Settings > Apps > VisionNav > Permissions.',
        );
      }
      throw CameraPermissionException('Camera permission denied.');
    }

    _cameras = await availableCameras();
    if (_cameras.isEmpty) {
      throw CameraPermissionException('No cameras found on this device.');
    }

    final selectedCamera = _selectRearCamera(_cameras);

    await _controller?.dispose();
    _controller = CameraController(
      selectedCamera,
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.yuv420,
    );

    try {
      await _controller!.initialize();
      _isInitialized = true;
      debugPrint('Camera initialized: ${selectedCamera.name} (${selectedCamera.lensDirection})');
    } catch (e) {
      _controller?.dispose();
      _controller = null;
      _isInitialized = false;
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
    if (!_isInitialized || _controller == null || !_controller!.value.isInitialized) {
      throw StateError('Camera is not initialized.');
    }
    if (_controller!.value.isTakingPicture) {
      throw StateError('Capture already in progress.');
    }
    final file = await _controller!.takePicture();
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

  Future<void> dispose() async {
    stopFrameStreaming();
    await _controller?.dispose();
    _controller = null;
    _isInitialized = false;
  }
}

import 'package:permission_handler/permission_handler.dart';

/// Android accepts one permission request at a time. Camera-first startup and
/// voice initialization can request permissions in the same frame.
Future<void> _permissionQueue = Future<void>.value();
Future<PermissionStatus> requestAppPermission(Permission permission) {
  final result = _permissionQueue.then((_) => permission.request());
  _permissionQueue = result.then<void>((_) {}, onError: (Object _) {});
  return result;
}

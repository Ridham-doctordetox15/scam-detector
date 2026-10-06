/// Picks a screenshot with Android's system photo picker (no storage permission needed).
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:image_picker/image_picker.dart';

const String _appId = 'io.github.ridhamsd1.scamchecker';

/// True only for files inside this app's private cache directory
/// (`/data/user/<n>/<appId>/cache/...` or `/data/data/<appId>/cache/...`).
bool isOwnCacheCopy(String path) =>
    RegExp('^/data/(user/\\d+|data)/${RegExp.escape(_appId)}/cache/').hasMatch(path) && !path.contains('/../');

/// Returns the chosen image's bytes, or null when the user cancels.
abstract class ScreenshotPicker {
  Future<Uint8List?> pick();
}

class SystemScreenshotPicker implements ScreenshotPicker {
  SystemScreenshotPicker({ImagePicker? picker}) : _picker = picker ?? ImagePicker();

  final ImagePicker _picker;

  @override
  Future<Uint8List?> pick() async {
    // No maxWidth/quality: re-encoding would change what OCR sees. requestFullMetadata: false
    // avoids asking for media-location access.
    final file = await _picker.pickImage(source: ImageSource.gallery, requestFullMetadata: false);
    if (file == null) return null;
    try {
      return await file.readAsBytes();
    } finally {
      // image_picker copies the picked image into the app's cache. Delete that copy straight
      // away so nothing stays on the device (the bytes live in memory only). The path check makes
      // sure only our own cache copy can ever be deleted, never a user's original photo.
      if (isOwnCacheCopy(file.path)) {
        try {
          final copy = File(file.path);
          await copy.delete();
          // image_picker puts each copy in its own folder; remove it once empty.
          final folder = copy.parent;
          final isSubfolder = isOwnCacheCopy('${folder.path}/x') && !folder.path.endsWith('/cache');
          if (isSubfolder && folder.listSync().isEmpty) await folder.delete();
        } on FileSystemException {
          // Already gone: nothing to clean up.
        }
      }
    }
  }
}

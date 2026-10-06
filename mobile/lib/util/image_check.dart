/// Screenshot checks done before upload. Same rules as the API (src/ocr/validate.py): the format
/// is sniffed from the file's magic bytes, never trusted from a name or MIME type.
library;

import 'dart:typed_data';

import '../config/limits.dart';

enum ImageFormat {
  png('png', 'image/png'),
  jpeg('jpg', 'image/jpeg'),
  webp('webp', 'image/webp');

  const ImageFormat(this.extension, this.mimeType);
  final String extension;
  final String mimeType;
}

/// PNG, JPEG or WebP from magic bytes, else null.
ImageFormat? sniffImageFormat(Uint8List data) {
  bool startsWith(List<int> sig) {
    if (data.length < sig.length) return false;
    for (var i = 0; i < sig.length; i++) {
      if (data[i] != sig[i]) return false;
    }
    return true;
  }

  if (startsWith(const [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])) return ImageFormat.png;
  if (startsWith(const [0xFF, 0xD8, 0xFF])) return ImageFormat.jpeg;
  if (data.length >= 12 &&
      startsWith(const [0x52, 0x49, 0x46, 0x46]) && // RIFF
      data[8] == 0x57 &&
      data[9] == 0x45 &&
      data[10] == 0x42 &&
      data[11] == 0x50) {
    // WEBP
    return ImageFormat.webp;
  }
  return null;
}

/// An error code from the API's vocabulary, or null when the image may be uploaded.
String? validateImageBytes(Uint8List data) {
  if (data.isEmpty) return 'empty';
  if (sniffImageFormat(data) == null) return 'unsupported_type';
  if (data.length > maxImageBytes) return 'too_large';
  return null;
}

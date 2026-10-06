import 'package:flutter/material.dart';

import 'api/api_client.dart';
import 'app.dart';
import 'config/api_config.dart';
import 'platform/screenshot_picker.dart';
import 'platform/share_receiver.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  registerFontLicences();
  runApp(
    ScamCheckerApp(
      api: ApiClient(config: ApiConfig.resolve()),
      picker: SystemScreenshotPicker(),
      shareReceiver: ChannelShareReceiver(),
    ),
  );
}

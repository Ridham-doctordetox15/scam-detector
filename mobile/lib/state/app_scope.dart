/// Hands the app's services to the widget tree. Tests build it with fakes.
library;

import 'package:flutter/widgets.dart';

import '../api/api_client.dart';
import '../platform/screenshot_picker.dart';
import 'controllers.dart';

class AppScope extends InheritedWidget {
  const AppScope({
    super.key,
    required this.api,
    required this.picker,
    required this.settings,
    required this.backend,
    required super.child,
  });

  final ApiClient api;
  final ScreenshotPicker picker;
  final AppSettings settings;
  final BackendStatus backend;

  static AppScope of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'No AppScope above this widget');
    return scope!;
  }

  @override
  bool updateShouldNotify(AppScope oldWidget) =>
      api != oldWidget.api ||
      picker != oldWidget.picker ||
      settings != oldWidget.settings ||
      backend != oldWidget.backend;
}

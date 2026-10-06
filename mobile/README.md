# Scam Message Checker: Android app

Flutter app (Android only) for the scam and phishing message detector. Paste a message, pick a
screenshot, or share one from SMS, WhatsApp or Gmail; the app shows the risk band, warning signs, an
explanation and what to do, in English or Hindi. It talks only to the project's API and stores
nothing on the phone.

```powershell
flutter pub get
flutter analyze
flutter test
flutter run            # debug build against http://127.0.0.1:7860 (use adb reverse tcp:7860 tcp:7860)
```

Setup, API address switching, release signing and publishing on GitHub Releases:
see [../docs/mobile.md](../docs/mobile.md).

```
lib/
  config/     api_config.dart (the ONE place for the API address), limits.dart
  api/        api_client.dart (the only network code), models.dart
  i18n/       strings.dart (lookup), mobile_strings.dart (app-only text)
  generated/  web_data.g.dart (web wording, samples, pattern names; node tool/sync_web_data.mjs)
  platform/   share_receiver.dart (share intent channel), screenshot_picker.dart
  state/      controllers.dart (ChangeNotifiers), app_scope.dart
  screens/    home, results, about
  widgets/    risk gauge/band, result view, feedback, error and status widgets
android/app/src/main/kotlin/.../MainActivity.kt   receives ACTION_SEND shares
```

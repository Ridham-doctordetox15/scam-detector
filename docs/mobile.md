# Android app (`mobile/`)

A Flutter app (Android only) that checks a message the same way the web app does: paste text, pick a
screenshot, or **share** a message or screenshot from SMS, WhatsApp, Gmail or any other app. It
uses the same four API endpoints as the web app (`/analyze/text`, `/analyze/image`, `/feedback`,
`/health`) and stores nothing on the phone. The APK is distributed through **GitHub Releases only**
(no Play Store).

- Package: `io.github.ridhamsd1.scamchecker` · App name: Scam Message Checker / स्कैम मैसेज जाँच
- Min Android version: 7.0 (API 24) · Permission: Internet only
- Dependencies: `http` (BSD-3), `image_picker` (Apache-2.0 + BSD-3, by flutter.dev),
  `flutter_localizations` (Flutter SDK). Fonts: Noto Sans + Noto Sans Devanagari (OFL 1.1), bundled.
  No Firebase, analytics, crash reporting or ads.

## Where the API address comes from

All in one file: [`mobile/lib/config/api_config.dart`](../mobile/lib/config/api_config.dart).

| Build | Address used |
|---|---|
| `flutter run` (debug) | `http://127.0.0.1:7860`: your computer's API, reached over USB with `adb reverse` |
| `flutter run --dart-define=API_URL=http://192.168.1.20:7860` | any other address (debug only, e.g. over Wi-Fi) |
| `flutter run --dart-define=API_TARGET=deployed` | the deployed API, from a debug build |
| `flutter build apk --release` | `deployedApiUrl` in `api_config.dart`. **Must be `https://`**; anything else is refused. |

While `deployedApiUrl` is empty, a release build shows "No analysis server is set up for this app
yet" and sends nothing. Plain HTTP is only possible in debug builds: the release build's Android
network security config blocks it as well (`android/app/src/main/res/xml/network_security_config.xml`).

## Run on your phone against the local API (YOU DO)

1. Start the API on your computer (see [deployment.md](deployment.md), "Run locally"):
   ```powershell
   .venv\Scripts\python -m uvicorn api.main:create_app --factory --port 7860 --workers 1 --no-access-log
   ```
2. Phone: Settings → About phone → tap **Build number** 7 times → Developer options → turn on
   **USB debugging**. Connect the USB cable and tap **Allow** on the "Allow USB debugging?" prompt
   (tick "Always allow from this computer").
3. Check the phone is visible (it must say `device`, not `unauthorized`):
   ```powershell
   & "$env:LOCALAPPDATA\Android\sdk\platform-tools\adb.exe" devices
   flutter devices
   ```
4. Forward the phone's port 7860 to your computer (repeat after every reconnect):
   ```powershell
   & "$env:LOCALAPPDATA\Android\sdk\platform-tools\adb.exe" reverse tcp:7860 tcp:7860
   ```
5. Run the app:
   ```powershell
   cd mobile
   flutter run
   ```
6. Try: paste a sample, pick a screenshot, then share a message from your SMS app and a screenshot
   from Gallery or WhatsApp ("Share" → Scam Message Checker).

## Release signing (YOU DO, once)

The release build reads its signing details from `mobile/android/key.properties`. Both that file and
the keystore are gitignored. **Keep the keystore outside the repository and back it up**: if you
lose it, you can't publish updates that install over the old version.

1. Create the keystore. It asks for a password and your name. Newer keytool versions don't ask for a
   separate key password; the key then uses the same password.
   ```powershell
   New-Item -ItemType Directory -Force "$env:USERPROFILE\keys" | Out-Null
   & "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe" -genkeypair -v `
     -keystore "$env:USERPROFILE\keys\scamchecker-release.jks" `
     -keyalg RSA -keysize 2048 -validity 10000 -alias scamchecker
   ```
2. Create `mobile/android/key.properties` (forward slashes in the path):
   ```properties
   storeFile=C:/Users/Admin/keys/scamchecker-release.jks
   storePassword=<the password you chose>
   keyAlias=scamchecker
   keyPassword=<the same password>
   ```
3. Without this file a release build stops with "Release signing is not set up: ...". This is
   deliberate, so an APK signed with the debug key can't be published by mistake.

## Build and publish a release (YOU DO, after the API is online)

1. Put the deployed API URL in `mobile/lib/config/api_config.dart`:
   ```dart
   const String deployedApiUrl = 'https://<you>-<space>.hf.space';
   ```
   Then check it from a debug build first:
   `flutter run --dart-define=API_TARGET=deployed`.
2. Bump the version in `mobile/pubspec.yaml` for every release (`version: 0.1.0+1` → `0.1.1+2`;
   the number after `+` must always go up).
3. Build:
   ```powershell
   cd mobile
   flutter analyze; flutter test
   flutter build apk --release
   Get-FileHash build\app\outputs\flutter-apk\app-release.apk -Algorithm SHA256
   ```
   The APK is at `mobile/build/app/outputs/flutter-apk/app-release.apk`.
4. Install it once on your phone to check it (`flutter install --release`, or copy the file over).
5. GitHub → your repository → **Releases** → **Draft a new release** → tag `mobile-v0.1.1` →
   attach `app-release.apk` (rename to `scam-message-checker-0.1.1.apk`) → paste the SHA-256 into the
   notes → **Publish release**.
6. Tell users in the release notes: Android will ask to allow installing from the browser/Files app
   ("Install unknown apps"), and Play Protect may warn about an app it doesn't know. Both are normal
   for apps outside the Play Store.

## Developing

- Interface text is shared with the web app. After changing `web/src/i18n/en.ts` or `hi.ts` (or the
  samples or pattern names), regenerate from `mobile/`: `node tool/sync_web_data.mjs`. A test fails if
  you forget. App-only text is in `lib/i18n/mobile_strings.dart`.
- `flutter analyze` and `flutter test` must both be clean before a release.
- Share handling is native Kotlin (`android/app/src/main/kotlin/.../MainActivity.kt`), no plugin.

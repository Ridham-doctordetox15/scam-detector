import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing details live in android/key.properties (gitignored, never committed):
//   storeFile=C:/Users/<you>/keys/scamchecker-release.jks
//   storePassword=...
//   keyAlias=scamchecker
//   keyPassword=...
// Release builds stop with a clear message when the file or a value is missing, so an APK signed
// with the debug key can never be published by accident. Debug builds don't need it.
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
val requiredSigningKeys = listOf("storeFile", "storePassword", "keyAlias", "keyPassword")
val signingProblem: String? = when {
    !keystorePropertiesFile.exists() ->
        "android/key.properties is missing. Create the upload keystore and key.properties first " +
            "(see docs/mobile.md, \"Release signing\")."
    else -> {
        FileInputStream(keystorePropertiesFile).use { keystoreProperties.load(it) }
        val missing = requiredSigningKeys.filter { keystoreProperties.getProperty(it).isNullOrBlank() }
        when {
            missing.isNotEmpty() -> "android/key.properties is missing: ${missing.joinToString()}."
            !file(keystoreProperties.getProperty("storeFile")).exists() ->
                "The keystore named in android/key.properties (storeFile) does not exist."
            else -> null
        }
    }
}

android {
    namespace = "io.github.ridhamsd1.scamchecker"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "io.github.ridhamsd1.scamchecker"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code and name from pubspec.yaml (version: 0.1.0+1).
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (signingProblem == null) {
            create("release") {
                storeFile = file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // Never falls back to the debug key (see the check below).
            signingConfig = if (signingProblem == null) signingConfigs.getByName("release") else null
        }
    }
}

// Fail early, before compiling, when a release build is requested without signing details.
gradle.taskGraph.whenReady {
    val wantsRelease = allTasks.any { task ->
        task.project == project && (task.name == "assembleRelease" || task.name == "bundleRelease")
    }
    if (wantsRelease && signingProblem != null) {
        throw GradleException("Release signing is not set up: $signingProblem")
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

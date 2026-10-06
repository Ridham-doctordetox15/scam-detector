package io.github.ridhamsd1.scamchecker

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayOutputStream
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Receives text and screenshots shared from other apps (ACTION_SEND) and hands them to Dart.
 *
 * Protocol (see lib/platform/share_receiver.dart), channel [CHANNEL]:
 *  - Dart calls `getInitialShare` once at start-up; it gets the share that launched the app, or null.
 *  - A share that arrives while the app is open is pushed to Dart with `onShare`.
 * Each share is a map: {kind: text, text}, {kind: image, bytes} or {kind: error, code}.
 *
 * Privacy: shared content is read into memory and passed on. Nothing is written to disk, logged,
 * or kept after it has been delivered.
 */
class MainActivity : FlutterActivity() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val io: ExecutorService = Executors.newSingleThreadExecutor()
    private var channel: MethodChannel? = null

    /** The intent that launched the app, until Dart asks for it (then cleared). */
    private var pendingIntent: Intent? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Re-created activity (e.g. after the process was killed in the background) or a launch
        // from Recents: the original share was already handled, so don't analyse it again.
        val fromHistory = (intent.flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY) != 0
        if (savedInstanceState == null && !fromHistory) pendingIntent = intent
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val ch = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
        ch.setMethodCallHandler { call, result ->
            when (call.method) {
                "getInitialShare" -> {
                    val launch = pendingIntent
                    pendingIntent = null
                    if (launch == null || !isShare(launch)) {
                        result.success(null)
                    } else {
                        readShare(launch) { share -> result.success(share) }
                    }
                }
                else -> result.notImplemented()
            }
        }
        channel = ch
    }

    /** A share while the app is already open (launchMode="singleTop"). */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (!isShare(intent)) return
        readShare(intent) { share -> channel?.invokeMethod("onShare", share) }
    }

    override fun onDestroy() {
        io.shutdownNow()
        channel?.setMethodCallHandler(null)
        channel = null
        super.onDestroy()
    }

    private fun isShare(intent: Intent): Boolean = intent.action == Intent.ACTION_SEND

    /** Reads the share off the main thread and replies on the main thread. */
    private fun readShare(intent: Intent, reply: (Map<String, Any>) -> Unit) {
        io.execute {
            val share = try {
                parseShare(intent)
            } catch (e: Exception) {
                // SecurityException, IOException, ... The details are not logged (privacy).
                shareError("read_failed")
            }
            mainHandler.post { reply(share) }
        }
    }

    private fun parseShare(intent: Intent): Map<String, Any> {
        val type = intent.type ?: return shareError("unsupported")
        if (type.startsWith("image/")) {
            val uri = streamUri(intent) ?: return shareError("read_failed")
            return readImage(uri)
        }
        if (type.startsWith("text/")) {
            val text = intent.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString()
            if (text.isNullOrBlank()) return shareError("unsupported")
            // Keep a little over the API's limit so the app can still say "too long" accurately,
            // without passing megabytes of text over the channel.
            return mapOf("kind" to "text", "text" to text.take(MAX_TEXT_CHARS_SENT))
        }
        return shareError("unsupported")
    }

    @Suppress("DEPRECATION")
    private fun streamUri(intent: Intent): Uri? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
        } else {
            intent.getParcelableExtra(Intent.EXTRA_STREAM)
        }

    /** Reads at most MAX_IMAGE_BYTES + 1 bytes, so a huge file can't exhaust memory. */
    private fun readImage(uri: Uri): Map<String, Any> {
        // Only content:// URIs from the sharing app; file:// could point at our own private files.
        if (uri.scheme != "content") return shareError("unsupported")
        val stream = contentResolver.openInputStream(uri) ?: return shareError("read_failed")
        stream.use { input ->
            val out = ByteArrayOutputStream()
            val buffer = ByteArray(64 * 1024)
            var total = 0
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
                total += n
                if (total > MAX_IMAGE_BYTES) return shareError("too_large")
                out.write(buffer, 0, n)
            }
            if (total == 0) return shareError("read_failed")
            return mapOf("kind" to "image", "bytes" to out.toByteArray())
        }
    }

    private fun shareError(code: String): Map<String, Any> = mapOf("kind" to "error", "code" to code)

    companion object {
        const val CHANNEL = "io.github.ridhamsd1.scamchecker/share"

        /** Same limit as the API and lib/config/limits.dart. */
        const val MAX_IMAGE_BYTES = 5 * 1024 * 1024

        /** The API allows 5000 characters; a few more are kept so "too long" is still detected. */
        const val MAX_TEXT_CHARS_SENT = 5001
    }
}

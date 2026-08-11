package com.amaksoft.notifrelay.testapp

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicInteger

/**
 * Scriptable notification source for the e2e verification harness (see
 * plan "End-to-end verification harness") — posts a real, actual system
 * notification with the given title/text/channel so the real
 * NotifRelayListenerService in the main app picks it up exactly like any
 * other app's notification. Write path mirrors the main app's
 * ContentProvider convention: a single call() method with a
 * base64-encoded JSON `json` extra, since `adb shell` re-tokenizes
 * unquoted argument text and would otherwise mangle anything with
 * spaces/quotes/colons in it.
 */
class NotifTestContentProvider : ContentProvider() {

    companion object {
        private val nextId = AtomicInteger(1)
    }

    override fun onCreate(): Boolean = true

    override fun call(method: String, arg: String?, extras: Bundle?): Bundle {
        val appContext = context?.applicationContext ?: return Bundle()
        val jsonB64 = extras?.getString("json") ?: return Bundle()
        val json = JSONObject(String(Base64.decode(jsonB64, Base64.DEFAULT)))

        if (method == "post") {
            val channelId = json.optString("channelId", Channels.CHANNEL_A)
            val title = json.optString("title", "Test notification")
            val text = json.optString("text", "")
            val notification = NotificationCompat.Builder(appContext, channelId)
                .setSmallIcon(R.drawable.ic_test_notification)
                .setContentTitle(title)
                .setContentText(text)
                .setAutoCancel(true)
                .build()
            NotificationManagerCompat.from(appContext).notify(nextId.getAndIncrement(), notification)
        }
        return Bundle()
    }

    override fun query(
        uri: Uri,
        projection: Array<out String>?,
        selection: String?,
        selectionArgs: Array<out String>?,
        sortOrder: String?,
    ): Cursor? = null

    override fun getType(uri: Uri): String? = null
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?): Int = 0
}

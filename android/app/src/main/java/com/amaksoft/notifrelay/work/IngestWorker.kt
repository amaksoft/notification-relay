package com.amaksoft.notifrelay.work

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.WorkerParameters
import com.google.firebase.functions.FirebaseFunctions
import kotlinx.coroutines.tasks.await

private const val TAG = "IngestWorker"

/**
 * Calls the ingestNotification Firebase Callable for a single notification
 * that an on-device rule already matched (see plan Architecture overview —
 * by the time this worker runs, the privacy decision is already made; this
 * is purely "deliver it"). WorkManager's own network-constraint + backoff
 * retry handles offline/flaky-network cases; no local queue table needed.
 */
class IngestWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val notification = hashMapOf<String, Any?>(
            "package" to inputData.getString(KEY_PACKAGE),
            "appName" to inputData.getString(KEY_APP_NAME),
            "title" to inputData.getString(KEY_TITLE),
            "text" to inputData.getString(KEY_TEXT),
            "channelId" to inputData.getString(KEY_CHANNEL_ID),
            "channelName" to inputData.getString(KEY_CHANNEL_NAME),
            "flags" to inputData.getInt(KEY_FLAGS, 0),
            "importance" to inputData.getInt(KEY_IMPORTANCE, 0),
            "timestamp" to inputData.getLong(KEY_TIMESTAMP, 0L),
            "key" to inputData.getString(KEY_NOTIF_KEY),
        )
        val payload = hashMapOf<String, Any?>("notification" to notification)

        return try {
            val result = FirebaseFunctions.getInstance()
                .getHttpsCallable("ingest_notification")
                .call(payload)
                .await()
            Log.i(TAG, "ingest_notification succeeded: ${result.data}")
            Result.success()
        } catch (e: Exception) {
            if (runAttemptCount < MAX_ATTEMPTS) {
                Log.w(TAG, "ingest_notification call failed (attempt $runAttemptCount), retrying", e)
                Result.retry()
            } else {
                Log.e(TAG, "ingest_notification call failed after $runAttemptCount attempts, giving up", e)
                Result.failure()
            }
        }
    }

    companion object {
        private const val MAX_ATTEMPTS = 5

        const val KEY_PACKAGE = "package"
        const val KEY_APP_NAME = "appName"
        const val KEY_TITLE = "title"
        const val KEY_TEXT = "text"
        const val KEY_CHANNEL_ID = "channelId"
        const val KEY_CHANNEL_NAME = "channelName"
        const val KEY_FLAGS = "flags"
        const val KEY_IMPORTANCE = "importance"
        const val KEY_TIMESTAMP = "timestamp"
        const val KEY_NOTIF_KEY = "notifKey"

        fun buildInputData(
            packageName: String,
            appName: String,
            title: String,
            text: String,
            channelId: String,
            channelName: String,
            flags: Int,
            importance: Int,
            timestamp: Long,
            notifKey: String,
        ): Data = Data.Builder()
            .putString(KEY_PACKAGE, packageName)
            .putString(KEY_APP_NAME, appName)
            .putString(KEY_TITLE, title)
            .putString(KEY_TEXT, text)
            .putString(KEY_CHANNEL_ID, channelId)
            .putString(KEY_CHANNEL_NAME, channelName)
            .putInt(KEY_FLAGS, flags)
            .putInt(KEY_IMPORTANCE, importance)
            .putLong(KEY_TIMESTAMP, timestamp)
            .putString(KEY_NOTIF_KEY, notifKey)
            .build()
    }
}

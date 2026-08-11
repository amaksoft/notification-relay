package com.amaksoft.notifrelay.service

import android.app.NotificationManager
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Constraints
import androidx.work.BackoffPolicy
import com.amaksoft.notifrelay.data.AppDatabase
import com.amaksoft.notifrelay.data.SeenChannelEntity
import com.amaksoft.notifrelay.rules.ConditionEvaluator
import com.amaksoft.notifrelay.work.IngestWorker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * The on-device privacy gate (see plan Architecture overview): every
 * notification is captured here, but nothing leaves the device unless it
 * matches at least one enabled Rule. Mirrors the reference app's actual
 * behavior of evaluating ALL enabled rules per notification (not
 * first-match-wins) and independently throttling each match.
 */
class NotifRelayListenerService : NotificationListenerService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    companion object {
        private const val TAG = "NotifRelayListener"
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.cancel()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        super.onNotificationPosted(sbn)
        if (sbn.packageName == applicationContext.packageName) return

        scope.launch {
            handleNotification(sbn)
        }
    }

    private suspend fun handleNotification(sbn: StatusBarNotification) {
        val db = AppDatabase.get(applicationContext)
        val extras = sbn.notification.extras
        val title = extras.getCharSequence(android.app.Notification.EXTRA_TITLE)?.toString().orEmpty()
        val text = extras.getCharSequence(android.app.Notification.EXTRA_TEXT)?.toString().orEmpty()
        val channelId = sbn.notification.channelId ?: ""
        val channel = try {
            getNotificationChannels(sbn.packageName, sbn.user).find { it.id == channelId }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to resolve channel $channelId for ${sbn.packageName}", e)
            null
        }
        val channelName = channel?.name?.toString() ?: channelId
        val importance = channel?.importance ?: NotificationManager.IMPORTANCE_DEFAULT
        val flags = sbn.notification.flags
        val appName = try {
            val pm = applicationContext.packageManager
            pm.getApplicationLabel(pm.getApplicationInfo(sbn.packageName, 0)).toString()
        } catch (e: Exception) {
            Log.w(TAG, "Failed to resolve app label for ${sbn.packageName}", e)
            sbn.packageName
        }

        if (channelId.isNotEmpty()) {
            db.seenChannelDao().upsert(
                SeenChannelEntity(
                    packageName = sbn.packageName,
                    channelId = channelId,
                    channelName = channelName,
                    lastSeenMillis = System.currentTimeMillis(),
                )
            )
        }

        val notificationJson = JSONObject().apply {
            put("package", sbn.packageName)
            put("appName", appName)
            put("title", title)
            put("text", text)
            put("channelId", channelId)
            put("channelName", channelName)
            put("flags", flags)
            put("importance", importance)
        }

        val now = System.currentTimeMillis()
        val enabledRules = db.ruleDao().getEnabled()
        Log.d(TAG, "onNotificationPosted ${sbn.packageName}/$channelId, evaluating ${enabledRules.size} enabled rule(s)")
        for (rule in enabledRules) {
            if (!ConditionEvaluator.ruleMatches(rule.toJson(), notificationJson)) continue
            if (!ConditionEvaluator.throttleAllows(rule.lastFiredAtMillis, rule.throttleSeconds, now)) {
                Log.d(TAG, "Rule '${rule.name}' matched but is throttled, skipping")
                continue
            }

            Log.i(TAG, "Rule '${rule.name}' matched ${sbn.packageName}/$channelId, enqueuing ingest")
            db.ruleDao().markFired(rule.id, now)
            enqueueIngest(sbn, notificationJson, appName)
        }
    }

    private fun enqueueIngest(sbn: StatusBarNotification, notification: JSONObject, appName: String) {
        val inputData = IngestWorker.buildInputData(
            packageName = notification.getString("package"),
            appName = appName,
            title = notification.getString("title"),
            text = notification.getString("text"),
            channelId = notification.getString("channelId"),
            channelName = notification.getString("channelName"),
            flags = notification.getInt("flags"),
            importance = notification.getInt("importance"),
            timestamp = sbn.postTime,
            notifKey = sbn.key,
        )
        val request = OneTimeWorkRequestBuilder<IngestWorker>()
            .setInputData(inputData)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(applicationContext).enqueue(request)
    }
}

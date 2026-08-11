package com.amaksoft.notifrelay.data

import androidx.room.Entity
import org.json.JSONObject

/**
 * A (package, channelId) pair the listener has actually observed, with
 * the human-readable channel name. Populated unconditionally on every
 * onNotificationPosted (see plan: "channel picker problem" — a
 * NotificationListenerService can't enumerate another app's channels
 * ahead of time, only ever discover them from notifications actually
 * received).
 */
@Entity(tableName = "seen_channels", primaryKeys = ["packageName", "channelId"])
data class SeenChannelEntity(
    val packageName: String,
    val channelId: String,
    val channelName: String,
    val lastSeenMillis: Long,
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("package", packageName)
        put("channelId", channelId)
        put("channelName", channelName)
        put("lastSeen", lastSeenMillis)
    }
}

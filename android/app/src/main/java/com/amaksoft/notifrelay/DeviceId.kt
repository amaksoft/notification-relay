package com.amaksoft.notifrelay

import android.content.Context
import java.util.UUID

/** A per-install device id, generated once and persisted — used as the
 * Firestore devices/{deviceId} document id. Not tied to any hardware
 * identifier (those are increasingly restricted); a random UUID is
 * sufficient since this only needs to be stable for one install. */
object DeviceId {
    private const val PREFS = "notifrelay"
    private const val KEY = "deviceId"

    fun get(context: Context): String {
        val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.getString(KEY, null)?.let { return it }
        val id = UUID.randomUUID().toString()
        prefs.edit().putString(KEY, id).apply()
        return id
    }
}

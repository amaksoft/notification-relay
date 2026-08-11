package com.amaksoft.notifrelay

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * No-op beyond logging — its only job is to make the system start this
 * app's process at boot (a manifest-registered BOOT_COMPLETED receiver
 * does that) rather than leaving the NotificationListenerService rebind
 * to whenever the OS next happens to launch the process. Confirmed via
 * decompiling the reference app (net.tative.notificationsrelay) that it
 * keeps an equivalent receiver for the same reason — some OEM battery
 * managers otherwise delay process start long enough to matter.
 */
class BootReceiver : BroadcastReceiver() {
    companion object {
        private const val TAG = "BootReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            Log.i(TAG, "Boot completed, notification listener should rebind shortly")
        }
    }
}

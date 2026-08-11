package com.amaksoft.notifrelay.testapp

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

object Channels {
    const val CHANNEL_A = "test_channel_a"
    const val CHANNEL_B = "test_channel_b"
}

class TestApp : Application() {
    override fun onCreate() {
        super.onCreate()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(
                NotificationChannel(Channels.CHANNEL_A, "Test channel A", NotificationManager.IMPORTANCE_DEFAULT)
            )
            manager.createNotificationChannel(
                NotificationChannel(Channels.CHANNEL_B, "Test channel B", NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
    }
}

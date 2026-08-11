package com.amaksoft.notifrelay

import android.content.Context
import android.content.pm.PackageManager
import android.graphics.drawable.Drawable

data class AppInfo(val packageName: String, val label: String)

object InstalledApps {
    fun list(context: Context): List<AppInfo> {
        val pm = context.packageManager
        return pm.getInstalledApplications(0)
            .filter { pm.getLaunchIntentForPackage(it.packageName) != null }
            .map { AppInfo(it.packageName, pm.getApplicationLabel(it).toString()) }
            .sortedBy { it.label.lowercase() }
    }

    /** Looked up lazily per row in the app picker UI (see
     * ui/components/AutocompleteField) rather than eagerly on every
     * AppInfo — list()'s other callers (device-status reporting to the
     * backend, the adb ContentProvider) only ever need package+label,
     * so there's no reason to decode every installed app's icon just to
     * answer those. */
    fun icon(context: Context, packageName: String): Drawable? =
        try {
            context.packageManager.getApplicationIcon(packageName)
        } catch (e: PackageManager.NameNotFoundException) {
            null
        }
}

package com.amaksoft.notifrelay.provider

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import com.amaksoft.notifrelay.InstalledApps
import com.amaksoft.notifrelay.data.AppDatabase
import com.amaksoft.notifrelay.data.RuleEntity
import kotlinx.coroutines.runBlocking
import org.json.JSONObject

/**
 * adb-driven local configuration surface — see docs/RULE_SCHEMA.md and
 * cli/notifrelay_cli/local_backend.py, which this must match exactly:
 * reads return one JSON-blob column per row (no generic multi-column
 * text format, which breaks once any field can itself contain commas);
 * writes go through call() with a base64-encoded JSON `json` extra
 * (sidesteps `adb shell`'s argument re-tokenization of anything with
 * spaces/quotes/colons in it).
 *
 * Trust boundary: exported with no extra permission — adb access already
 * implies USB debugging is enabled, which is already a significant trust
 * boundary (see plan).
 */
class NotifRelayContentProvider : ContentProvider() {

    override fun onCreate(): Boolean = true

    override fun query(
        uri: Uri,
        projection: Array<out String>?,
        selection: String?,
        selectionArgs: Array<out String>?,
        sortOrder: String?,
    ): Cursor? {
        val appContext = context?.applicationContext ?: return null
        val db = AppDatabase.get(appContext)

        return when (uri.lastPathSegment) {
            "rules" -> {
                val rules = runBlocking { db.ruleDao().getAll() }
                MatrixCursor(arrayOf("ruleJson")).apply {
                    rules.forEach { addRow(arrayOf(it.toJson().toString())) }
                }
            }
            "apps" -> {
                MatrixCursor(arrayOf("appJson")).apply {
                    InstalledApps.list(appContext).forEach {
                        val json = JSONObject().put("package", it.packageName).put("label", it.label)
                        addRow(arrayOf(json.toString()))
                    }
                }
            }
            "channels" -> {
                val channels = runBlocking { db.seenChannelDao().getAll() }
                MatrixCursor(arrayOf("channelJson")).apply {
                    channels.forEach { addRow(arrayOf(it.toJson().toString())) }
                }
            }
            else -> null
        }
    }

    override fun call(method: String, arg: String?, extras: Bundle?): Bundle {
        val appContext = context?.applicationContext ?: return Bundle()
        val db = AppDatabase.get(appContext)
        val jsonB64 = extras?.getString("json")
        if (jsonB64 == null) return Bundle()
        val json = JSONObject(String(Base64.decode(jsonB64, Base64.DEFAULT)))

        runBlocking {
            when (method) {
                "addRule" -> db.ruleDao().upsert(RuleEntity.fromJson(json))
                "setRuleEnabled" -> db.ruleDao().setEnabled(json.getString("id"), json.getBoolean("enabled"))
                "removeRule" -> db.ruleDao().deleteById(json.getString("id"))
            }
        }
        return Bundle()
    }

    override fun getType(uri: Uri): String? = null
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?): Int = 0
}

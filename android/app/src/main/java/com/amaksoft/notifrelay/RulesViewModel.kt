package com.amaksoft.notifrelay

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.amaksoft.notifrelay.data.AppDatabase
import com.amaksoft.notifrelay.data.RuleEntity
import com.amaksoft.notifrelay.data.SeenChannelEntity
import com.google.firebase.functions.FirebaseFunctions
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

class RulesViewModel(application: Application) : AndroidViewModel(application) {

    companion object {
        private const val TAG = "RulesViewModel"
    }

    private val db = AppDatabase.get(application)

    val rules: StateFlow<List<RuleEntity>> = db.ruleDao().observeAll()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val installedApps: List<AppInfo> = InstalledApps.list(application)

    private val _seenChannels = MutableStateFlow<List<SeenChannelEntity>>(emptyList())
    val seenChannels: StateFlow<List<SeenChannelEntity>> = _seenChannels

    fun loadChannelsFor(packageName: String) {
        viewModelScope.launch {
            _seenChannels.value = db.seenChannelDao().getForPackage(packageName)
        }
    }

    fun toggleRule(rule: RuleEntity, enabled: Boolean) = viewModelScope.launch {
        db.ruleDao().setEnabled(rule.id, enabled)
        syncToBackend()
    }

    fun deleteRule(rule: RuleEntity) = viewModelScope.launch {
        db.ruleDao().delete(rule)
        syncToBackend()
    }

    fun addRule(name: String, packageName: String, channelId: String?) = viewModelScope.launch {
        val condition = buildSimpleCondition(packageName, channelId)
        val rule = RuleEntity(
            id = UUID.randomUUID().toString().take(12),
            name = name,
            conditionJson = condition.toString(),
        )
        db.ruleDao().upsert(rule)
        syncToBackend()
    }

    /** Mirrors cli/notifrelay_cli/conditions.py build_simple_condition for
     * the common package(+channel) case. */
    private fun buildSimpleCondition(pkg: String, channel: String?): JSONObject {
        val packageLeaf = JSONObject().put("type", "NOTIFICATION_PACKAGE_NAME").put("stringValue", pkg)
        if (channel.isNullOrBlank()) return packageLeaf
        val channelLeaf = JSONObject().put("type", "NOTIFICATION_CHANNEL_ID").put("stringValue", channel)
        return JSONObject().put("type", "AND").put(
            "conditions",
            JSONArray().put(packageLeaf).put(channelLeaf)
        )
    }

    private suspend fun syncToBackend() {
        val rulesList = db.ruleDao().getAll().map { it.toJson() }.map { obj ->
            obj.keys().asSequence().associateWith { key -> obj.get(key) }
        }
        val payload = hashMapOf<String, Any?>(
            "deviceId" to DeviceId.get(getApplication()),
            "rules" to rulesList,
        )
        try {
            FirebaseFunctions.getInstance().getHttpsCallable("update_device_rules").call(payload)
        } catch (e: Exception) {
            // Best-effort mirror to Firestore; on-device state (just
            // written to Room above) is already the source of truth for
            // actual filtering. Still logged so a persistent failure is
            // actually diagnosable.
            Log.w(TAG, "update_device_rules call failed", e)
        }
    }
}

package com.amaksoft.notifrelay.data

import androidx.room.Entity
import androidx.room.PrimaryKey
import org.json.JSONObject

/**
 * On-device Rule row — see docs/RULE_SCHEMA.md. `conditionJson` stores
 * the recursive Condition tree as a JSON string (see rules/ConditionEvaluator
 * for why we don't model it as typed Room columns).
 */
@Entity(tableName = "rules")
data class RuleEntity(
    @PrimaryKey val id: String,
    val name: String,
    val conditionJson: String,
    val throttleSeconds: Int = 0,
    val enabled: Boolean = true,
    val order: Int = 0,
    val format: String = "DEFAULT",
    val lastFiredAtMillis: Long? = null,
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("id", id)
        put("name", name)
        put("condition", JSONObject(conditionJson))
        put("throttleSeconds", throttleSeconds)
        put("enabled", enabled)
        put("order", order)
        put("format", format)
    }

    companion object {
        fun fromJson(json: JSONObject): RuleEntity = RuleEntity(
            id = json.optString("id").ifEmpty { java.util.UUID.randomUUID().toString().take(12) },
            name = json.optString("name"),
            conditionJson = json.getJSONObject("condition").toString(),
            throttleSeconds = json.optInt("throttleSeconds", 0),
            enabled = json.optBoolean("enabled", true),
            order = json.optInt("order", 0),
            format = json.optString("format", "DEFAULT"),
        )
    }
}

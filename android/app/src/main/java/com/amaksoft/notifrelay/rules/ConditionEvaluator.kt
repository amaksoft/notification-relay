package com.amaksoft.notifrelay.rules

import org.json.JSONObject

/**
 * On-device Condition/Rule evaluator. MUST stay semantically identical to
 * functions/condition_matcher.py — see docs/RULE_SCHEMA.md, the single
 * source of truth for this schema. Cross-language fixtures live in
 * functions/tests/condition_fixtures.json; ConditionEvaluatorTest loads
 * that same file so the two implementations can't silently drift apart.
 *
 * Deliberately works directly on JSONObject rather than typed data
 * classes, mirroring the Python side's plain-dict approach — the schema
 * is recursive-but-flat-shaped (one node type with different optional
 * fields per leaf kind), which maps awkwardly onto Kotlin sealed classes
 * without a lot of ceremony for no real benefit here.
 */
object ConditionEvaluator {

    fun evaluate(condition: JSONObject, notification: JSONObject): Boolean {
        val type = condition.optString("type")
        val children = condition.optJSONArray("conditions")

        val result = when (type) {
            "ALWAYS" -> true
            "AND" -> children != null && children.length() > 0 && (0 until children.length()).all {
                evaluate(children.getJSONObject(it), notification)
            }
            "OR" -> children != null && children.length() > 0 && (0 until children.length()).any {
                evaluate(children.getJSONObject(it), notification)
            }
            "NOTIFICATION_TITLE" -> contains(notification.optString("title"), condition.optString("stringValue"))
            "NOTIFICATION_TEXT" -> contains(notification.optString("text"), condition.optString("stringValue"))
            "NOTIFICATION_PACKAGE_NAME" -> notification.optString("package") == condition.optString("stringValue")
            "NOTIFICATION_CHANNEL_ID" -> notification.optString("channelId") == condition.optString("stringValue")
            "NOTIFICATION_DEVICE_ID" -> notification.optString("deviceId") == condition.optString("stringValue")
            "NOTIFICATION_FLAG_SET" -> {
                val flags = notification.optInt("flags", 0)
                val mask = condition.optInt("intValue", 0)
                (flags and mask) != 0
            }
            else -> throw IllegalArgumentException("Unknown condition type: $type")
        }

        return if (condition.optBoolean("inverse", false)) !result else result
    }

    fun ruleMatches(rule: JSONObject, notification: JSONObject): Boolean {
        if (!rule.optBoolean("enabled", true)) return false
        return evaluate(rule.getJSONObject("condition"), notification)
    }

    /** Pure per-rule cooldown check — mirrors condition_matcher.throttle_allows. */
    fun throttleAllows(lastFiredAtMillis: Long?, throttleSeconds: Int, nowMillis: Long): Boolean {
        if (throttleSeconds <= 0) return true
        if (lastFiredAtMillis == null) return true
        return (nowMillis - lastFiredAtMillis) >= throttleSeconds * 1000L
    }

    private fun contains(haystack: String?, needle: String?): Boolean {
        return (haystack ?: "").lowercase().contains((needle ?: "").lowercase())
    }
}

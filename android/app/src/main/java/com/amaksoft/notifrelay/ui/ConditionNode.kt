package com.amaksoft.notifrelay.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateList
import org.json.JSONArray
import org.json.JSONObject

enum class NodeKind {
    AND, OR, PACKAGE, CHANNEL, TITLE, TEXT, FLAGS, ALWAYS;

    val isGroup: Boolean get() = this == AND || this == OR

    val schemaType: String
        get() = when (this) {
            AND -> "AND"
            OR -> "OR"
            PACKAGE -> "NOTIFICATION_PACKAGE_NAME"
            CHANNEL -> "NOTIFICATION_CHANNEL_ID"
            TITLE -> "NOTIFICATION_TITLE"
            TEXT -> "NOTIFICATION_TEXT"
            FLAGS -> "NOTIFICATION_FLAG_SET"
            ALWAYS -> "ALWAYS"
        }

    companion object {
        fun fromSchemaType(type: String): NodeKind = when (type) {
            "AND" -> AND
            "OR" -> OR
            "NOTIFICATION_PACKAGE_NAME" -> PACKAGE
            "NOTIFICATION_CHANNEL_ID" -> CHANNEL
            "NOTIFICATION_TITLE" -> TITLE
            "NOTIFICATION_TEXT" -> TEXT
            "NOTIFICATION_FLAG_SET" -> FLAGS
            else -> ALWAYS
        }
    }
}

/**
 * Mutable, Compose-state-backed mirror of the Condition schema (see
 * docs/RULE_SCHEMA.md) — used only by the tree-editor UI; converted
 * to/from the plain-JSON wire format at the edges (toJson/fromJson)
 * rather than editing JSONObject directly, since granular per-field
 * Compose recomposition is much simpler against real mutable state.
 */
class ConditionNode(
    kind: NodeKind,
    stringValue: String = "",
    intValue: String = "",
    inverse: Boolean = false,
) {
    var kind by mutableStateOf(kind)
    var stringValue by mutableStateOf(stringValue)
    var intValue by mutableStateOf(intValue)
    var inverse by mutableStateOf(inverse)
    val children: SnapshotStateList<ConditionNode> = mutableStateListOf()

    fun toJson(): JSONObject = JSONObject().apply {
        put("type", kind.schemaType)
        if (inverse) put("inverse", true)
        when {
            kind.isGroup -> put("conditions", JSONArray().apply { children.forEach { put(it.toJson()) } })
            kind == NodeKind.FLAGS -> put("intValue", intValue.toIntOrNull() ?: 0)
            kind == NodeKind.ALWAYS -> {}
            else -> put("stringValue", stringValue)
        }
    }

    companion object {
        fun fromJson(json: JSONObject): ConditionNode {
            val kind = NodeKind.fromSchemaType(json.optString("type"))
            val node = ConditionNode(
                kind = kind,
                stringValue = json.optString("stringValue", ""),
                intValue = if (json.has("intValue")) json.optInt("intValue").toString() else "",
                inverse = json.optBoolean("inverse", false),
            )
            if (kind.isGroup) {
                val children = json.optJSONArray("conditions")
                if (children != null) {
                    for (i in 0 until children.length()) {
                        node.children.add(fromJson(children.getJSONObject(i)))
                    }
                }
            }
            return node
        }

        /** A sensible default starting point for a brand-new rule: an AND
         * group with one empty package condition, so the tree editor
         * never opens on a totally blank canvas. */
        fun newDefault(): ConditionNode = ConditionNode(NodeKind.AND).apply {
            children.add(ConditionNode(NodeKind.PACKAGE))
        }
    }
}

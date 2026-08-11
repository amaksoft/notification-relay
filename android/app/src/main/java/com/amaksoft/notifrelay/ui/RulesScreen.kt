package com.amaksoft.notifrelay.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsBottomHeight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Button
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.amaksoft.notifrelay.AppInfo
import com.amaksoft.notifrelay.data.RuleEntity
import com.amaksoft.notifrelay.data.SeenChannelEntity
import com.amaksoft.notifrelay.ui.components.ConditionTreeEditor
import org.json.JSONObject

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RulesScreen(
    rules: List<RuleEntity>,
    installedApps: List<AppInfo>,
    seenChannels: List<SeenChannelEntity>,
    onToggle: (RuleEntity, Boolean) -> Unit,
    onDelete: (RuleEntity) -> Unit,
    onAddRule: (name: String, condition: JSONObject, throttleSeconds: Int) -> Unit,
    onUpdateRule: (id: String, name: String, condition: JSONObject, throttleSeconds: Int) -> Unit,
) {
    var editingRule by remember { mutableStateOf<RuleEntity?>(null) }
    var creatingNew by remember { mutableStateOf(false) }

    Scaffold(
        topBar = { CenterAlignedTopAppBar(title = { Text("Forwarding rules") }) },
        floatingActionButton = {
            FloatingActionButton(onClick = { creatingNew = true }) {
                Icon(Icons.Default.Add, contentDescription = "Add rule")
            }
        },
    ) { padding ->
        if (rules.isEmpty()) {
            Box(Modifier.padding(padding).fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    "No rules yet. Notifications are only forwarded for apps/channels you add a rule for.",
                    textAlign = TextAlign.Center,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(32.dp),
                )
            }
        } else {
            LazyColumn(
                modifier = Modifier.padding(padding).fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(rules, key = { it.id }) { rule ->
                    RuleCard(
                        rule = rule,
                        onToggle = { onToggle(rule, it) },
                        onDelete = { onDelete(rule) },
                        onEdit = { editingRule = rule },
                    )
                }
            }
        }
    }

    if (creatingNew) {
        RuleEditorSheet(
            existingRule = null,
            installedApps = installedApps,
            seenChannels = seenChannels,
            onDismiss = { creatingNew = false },
            onSubmit = { name, condition, throttle ->
                onAddRule(name, condition, throttle)
                creatingNew = false
            },
        )
    }
    editingRule?.let { rule ->
        RuleEditorSheet(
            existingRule = rule,
            installedApps = installedApps,
            seenChannels = seenChannels,
            onDismiss = { editingRule = null },
            onSubmit = { name, condition, throttle ->
                onUpdateRule(rule.id, name, condition, throttle)
                editingRule = null
            },
        )
    }
}

@Composable
private fun RuleCard(rule: RuleEntity, onToggle: (Boolean) -> Unit, onDelete: () -> Unit, onEdit: () -> Unit) {
    ElevatedCard(modifier = Modifier.fillMaxWidth(), onClick = onEdit) {
        Row(
            modifier = Modifier.padding(16.dp).fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(rule.name, style = MaterialTheme.typography.titleMedium)
                Text(
                    summarize(rule),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Switch(checked = rule.enabled, onCheckedChange = onToggle)
            IconButton(onClick = onDelete) {
                Icon(Icons.Default.Delete, contentDescription = "Remove rule", tint = MaterialTheme.colorScheme.error)
            }
        }
    }
}

private fun summarize(rule: RuleEntity): String {
    val parts = mutableListOf<String>()
    collectLeaves(JSONObject(rule.conditionJson), parts)
    val throttle = if (rule.throttleSeconds > 0) " · throttled ${rule.throttleSeconds}s" else ""
    val joiner = if (JSONObject(rule.conditionJson).optString("type") == "OR") " OR " else " AND "
    return parts.joinToString(joiner) + throttle
}

private fun collectLeaves(condition: JSONObject, out: MutableList<String>) {
    val inverse = if (condition.optBoolean("inverse", false)) "NOT " else ""
    when (val type = condition.optString("type")) {
        "AND", "OR" -> {
            val children = condition.optJSONArray("conditions") ?: return
            for (i in 0 until children.length()) collectLeaves(children.getJSONObject(i), out)
        }
        "NOTIFICATION_PACKAGE_NAME" -> out.add("${inverse}package=${condition.optString("stringValue")}")
        "NOTIFICATION_CHANNEL_ID" -> out.add("${inverse}channel=${condition.optString("stringValue")}")
        "NOTIFICATION_TITLE" -> out.add("${inverse}title~${condition.optString("stringValue")}")
        "NOTIFICATION_TEXT" -> out.add("${inverse}text~${condition.optString("stringValue")}")
        "NOTIFICATION_FLAG_SET" -> out.add("${inverse}flags&${condition.optInt("intValue")}")
        "ALWAYS" -> out.add("${inverse}always")
        else -> out.add("$inverse$type")
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RuleEditorSheet(
    existingRule: RuleEntity?,
    installedApps: List<AppInfo>,
    seenChannels: List<SeenChannelEntity>,
    onDismiss: () -> Unit,
    onSubmit: (name: String, condition: JSONObject, throttleSeconds: Int) -> Unit,
) {
    var name by remember { mutableStateOf(existingRule?.name ?: "") }
    var throttleText by remember { mutableStateOf((existingRule?.throttleSeconds ?: 0).toString()) }
    val root = remember {
        existingRule?.let { ConditionNode.fromJson(JSONObject(it.conditionJson)) } ?: ConditionNode.newDefault()
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState()) {
        Column(
            modifier = Modifier.padding(horizontal = 24.dp).padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(if (existingRule == null) "New rule" else "Edit rule", style = MaterialTheme.typography.titleLarge)

            OutlinedTextField(
                value = name,
                onValueChange = { name = it },
                label = { Text("Rule name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            OutlinedTextField(
                value = throttleText,
                onValueChange = { throttleText = it.filter { c -> c.isDigit() } },
                label = { Text("Throttle (seconds, 0 = no cooldown)") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth(),
            )

            Text(
                "Condition — combine AND/OR groups and NOT toggles freely; " +
                    "app/channel values always come from what's actually on this device.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            ConditionTreeEditor(
                node = root,
                installedApps = installedApps,
                seenChannels = seenChannels,
            )

            // Deliberately not wrapped in remember(): Compose's snapshot
            // system already tracks every mutableStateOf read that
            // happens during this function's execution (kind/stringValue/
            // intValue on every node, and each group's children list),
            // so this recomposes correctly on any nested edit anywhere in
            // the tree. A remember() keyed on something coarser (e.g.
            // child count) would miss leaf-value edits entirely.
            val hasAnyLeafValue = treeHasUsableLeaf(root)
            Button(
                onClick = {
                    onSubmit(name.trim(), root.toJson(), throttleText.toIntOrNull() ?: 0)
                },
                enabled = name.isNotBlank() && hasAnyLeafValue,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (existingRule == null) "Add rule" else "Save changes")
            }

            Spacer(Modifier.windowInsetsBottomHeight(WindowInsets.systemBars))
        }
    }
}

private fun treeHasUsableLeaf(node: ConditionNode): Boolean {
    if (node.kind.isGroup) return node.children.isNotEmpty() && node.children.all { treeHasUsableLeaf(it) }
    return when (node.kind) {
        NodeKind.PACKAGE, NodeKind.CHANNEL, NodeKind.TITLE, NodeKind.TEXT -> node.stringValue.isNotBlank()
        NodeKind.FLAGS -> node.intValue.isNotBlank()
        else -> true
    }
}

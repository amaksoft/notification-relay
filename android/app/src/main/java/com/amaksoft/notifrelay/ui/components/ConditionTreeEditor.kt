package com.amaksoft.notifrelay.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.amaksoft.notifrelay.AppInfo
import com.amaksoft.notifrelay.data.SeenChannelEntity
import com.amaksoft.notifrelay.ui.NodeKind
import com.amaksoft.notifrelay.ui.ConditionNode

private val LeafKinds = listOf(NodeKind.PACKAGE, NodeKind.CHANNEL, NodeKind.TITLE, NodeKind.TEXT, NodeKind.FLAGS, NodeKind.ALWAYS)

private fun NodeKind.displayName(): String = when (this) {
    NodeKind.PACKAGE -> "App"
    NodeKind.CHANNEL -> "Channel"
    NodeKind.TITLE -> "Title contains"
    NodeKind.TEXT -> "Text contains"
    NodeKind.FLAGS -> "Flag bitmask"
    NodeKind.ALWAYS -> "Always match"
    NodeKind.AND -> "AND"
    NodeKind.OR -> "OR"
}

/**
 * Recursive AND/OR/NOT Condition-tree editor — see docs/RULE_SCHEMA.md
 * and ui/ConditionNode.kt for the underlying model. Root is always a
 * group node (AND/OR); leaves are picked from real device data
 * (installed apps, seen channels) via AutocompleteField wherever
 * possible, same "never free-type something we can offer as a list"
 * rule as the rest of the app.
 */
@Composable
fun ConditionTreeEditor(
    node: ConditionNode,
    installedApps: List<AppInfo>,
    seenChannels: List<SeenChannelEntity>,
    depth: Int = 0,
    onRemove: (() -> Unit)? = null,
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            if (node.kind.isGroup) {
                GroupKindSelector(node)
            } else {
                LeafKindSelector(node)
            }
            Spacer(Modifier.width(8.dp))
            FilterChip(
                selected = node.inverse,
                onClick = { node.inverse = !node.inverse },
                label = { Text("NOT") },
            )
            Spacer(Modifier.weight(1f))
            if (onRemove != null) {
                IconButton(onClick = onRemove) {
                    Icon(Icons.Default.Close, contentDescription = "Remove condition")
                }
            }
        }

        Spacer(Modifier.height(4.dp))

        if (node.kind.isGroup) {
            Card(
                modifier = Modifier.padding(start = 16.dp).fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerHigh),
            ) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    node.children.forEachIndexed { index, child ->
                        ConditionTreeEditor(
                            node = child,
                            installedApps = installedApps,
                            seenChannels = seenChannels,
                            depth = depth + 1,
                            onRemove = { node.children.removeAt(index) },
                        )
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { node.children.add(ConditionNode(NodeKind.PACKAGE)) }) {
                            Text("+ Condition")
                        }
                        TextButton(onClick = { node.children.add(ConditionNode(NodeKind.AND)) }) {
                            Text("+ Group")
                        }
                    }
                }
            }
        } else {
            LeafValueEditor(node, installedApps, seenChannels)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun GroupKindSelector(node: ConditionNode) {
    SingleChoiceSegmentedButtonRow {
        listOf(NodeKind.AND, NodeKind.OR).forEachIndexed { index, kind ->
            SegmentedButton(
                selected = node.kind == kind,
                onClick = { node.kind = kind },
                shape = SegmentedButtonDefaults.itemShape(index = index, count = 2),
            ) {
                Text(kind.displayName())
            }
        }
    }
}

@Composable
private fun LeafKindSelector(node: ConditionNode) {
    var expanded by remember { mutableStateOf(false) }
    AssistChip(onClick = { expanded = true }, label = { Text(node.kind.displayName()) })
    DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
        LeafKinds.forEach { kind ->
            DropdownMenuItem(
                text = { Text(kind.displayName()) },
                onClick = {
                    node.kind = kind
                    node.stringValue = ""
                    node.intValue = ""
                    expanded = false
                },
            )
        }
    }
}

@Composable
private fun LeafValueEditor(node: ConditionNode, installedApps: List<AppInfo>, seenChannels: List<SeenChannelEntity>) {
    when (node.kind) {
        NodeKind.PACKAGE -> AutocompleteField(
            label = "App",
            options = installedApps,
            optionLabel = { it.label },
            optionSubtitle = { it.packageName },
            onOptionSelected = { node.stringValue = it.packageName },
            initialQuery = installedApps.find { it.packageName == node.stringValue }?.label ?: "",
            leadingIcon = { app -> AppIcon(app.packageName) },
            modifier = Modifier.fillMaxWidth(),
        )
        NodeKind.CHANNEL -> AutocompleteField(
            label = "Channel",
            options = seenChannels,
            optionLabel = { it.channelName },
            optionSubtitle = { "${it.packageName} · ${it.channelId}" },
            onOptionSelected = { node.stringValue = it.channelId },
            initialQuery = seenChannels.find { it.channelId == node.stringValue }?.channelName ?: node.stringValue,
            modifier = Modifier.fillMaxWidth(),
        )
        NodeKind.TITLE -> OutlinedTextField(
            value = node.stringValue,
            onValueChange = { node.stringValue = it },
            label = { Text("Title contains") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        NodeKind.TEXT -> OutlinedTextField(
            value = node.stringValue,
            onValueChange = { node.stringValue = it },
            label = { Text("Text contains") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        NodeKind.FLAGS -> OutlinedTextField(
            value = node.intValue,
            onValueChange = { node.intValue = it.filter { c -> c.isDigit() } },
            label = { Text("Flag bitmask") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth(),
        )
        NodeKind.ALWAYS -> Text(
            "Matches every notification",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        else -> {}
    }
}

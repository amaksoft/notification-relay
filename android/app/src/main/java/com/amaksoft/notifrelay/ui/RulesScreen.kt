package com.amaksoft.notifrelay.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsBottomHeight
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.graphics.drawable.toBitmap
import com.amaksoft.notifrelay.AppInfo
import com.amaksoft.notifrelay.InstalledApps
import com.amaksoft.notifrelay.data.RuleEntity
import com.amaksoft.notifrelay.data.SeenChannelEntity
import com.amaksoft.notifrelay.ui.components.AutocompleteField
import org.json.JSONObject

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RulesScreen(
    rules: List<RuleEntity>,
    installedApps: List<AppInfo>,
    seenChannels: List<SeenChannelEntity>,
    onPackageSelected: (String) -> Unit,
    onToggle: (RuleEntity, Boolean) -> Unit,
    onDelete: (RuleEntity) -> Unit,
    onAddRule: (name: String, pkg: String, channelId: String?) -> Unit,
) {
    var showSheet by remember { mutableStateOf(false) }

    Scaffold(
        topBar = { CenterAlignedTopAppBar(title = { Text("Forwarding rules") }) },
        floatingActionButton = {
            FloatingActionButton(onClick = { showSheet = true }) {
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
                    RuleCard(rule, onToggle = { onToggle(rule, it) }, onDelete = { onDelete(rule) })
                }
            }
        }
    }

    if (showSheet) {
        AddRuleSheet(
            installedApps = installedApps,
            seenChannels = seenChannels,
            onPackageSelected = onPackageSelected,
            onDismiss = { showSheet = false },
            onSubmit = { name, pkg, channel ->
                onAddRule(name, pkg, channel)
                showSheet = false
            },
        )
    }
}

@Composable
private fun RuleCard(rule: RuleEntity, onToggle: (Boolean) -> Unit, onDelete: () -> Unit) {
    ElevatedCard(modifier = Modifier.fillMaxWidth()) {
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
    return parts.joinToString(" AND ") + throttle
}

private fun collectLeaves(condition: JSONObject, out: MutableList<String>) {
    when (val type = condition.optString("type")) {
        "AND", "OR" -> {
            val children = condition.optJSONArray("conditions") ?: return
            for (i in 0 until children.length()) collectLeaves(children.getJSONObject(i), out)
        }
        "NOTIFICATION_PACKAGE_NAME" -> out.add("package=${condition.optString("stringValue")}")
        "NOTIFICATION_CHANNEL_ID" -> out.add("channel=${condition.optString("stringValue")}")
        "NOTIFICATION_TITLE" -> out.add("title~${condition.optString("stringValue")}")
        "NOTIFICATION_TEXT" -> out.add("text~${condition.optString("stringValue")}")
        else -> out.add(type)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddRuleSheet(
    installedApps: List<AppInfo>,
    seenChannels: List<SeenChannelEntity>,
    onPackageSelected: (String) -> Unit,
    onDismiss: () -> Unit,
    onSubmit: (name: String, pkg: String, channelId: String?) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var selectedPackage by remember { mutableStateOf<String?>(null) }
    var selectedChannel by remember { mutableStateOf<String?>(null) }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState()) {
        Column(
            modifier = Modifier.padding(horizontal = 24.dp).padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("New rule", style = MaterialTheme.typography.titleLarge)

            OutlinedTextField(
                value = name,
                onValueChange = { name = it },
                label = { Text("Rule name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            // Autocomplete picker constrained to installed apps — never
            // free-typed, so the submitted package always actually
            // exists on the device (see plan/UX feedback: no typo-prone
            // manual entry for anything we can offer as a list instead).
            AutocompleteField(
                label = "App",
                options = installedApps,
                optionLabel = { it.label },
                optionSubtitle = { it.packageName },
                onOptionSelected = {
                    selectedPackage = it.packageName
                    selectedChannel = null
                    onPackageSelected(it.packageName)
                },
                leadingIcon = { app -> AppIcon(app.packageName) },
                modifier = Modifier.fillMaxWidth(),
            )

            // Channel options are only ever what's actually been
            // observed for the selected app (see plan "channel picker
            // problem") — optional, so leaving it blank matches the
            // whole package.
            AutocompleteField(
                label = "Channel (optional)",
                options = seenChannels,
                optionLabel = { it.channelName },
                optionSubtitle = { it.channelId },
                onOptionSelected = { selectedChannel = it.channelId },
                enabled = selectedPackage != null,
                supportingText = if (selectedPackage != null && seenChannels.isEmpty()) {
                    "No channels seen yet for this app — leave blank to match any channel"
                } else null,
                modifier = Modifier.fillMaxWidth(),
            )

            Button(
                onClick = { onSubmit(name.trim(), selectedPackage!!, selectedChannel) },
                enabled = name.isNotBlank() && selectedPackage != null,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Add rule")
            }

            Spacer(Modifier.windowInsetsBottomHeight(WindowInsets.systemBars))
        }
    }
}

@Composable
private fun AppIcon(packageName: String) {
    val context = LocalContext.current
    val bitmap = remember(packageName) {
        InstalledApps.icon(context, packageName)?.toBitmap(width = 96, height = 96)?.asImageBitmap()
    }
    if (bitmap != null) {
        Image(bitmap = bitmap, contentDescription = null, modifier = Modifier.size(32.dp))
    } else {
        Spacer(Modifier.size(32.dp))
    }
}

package com.amaksoft.notifrelay.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    signedInEmail: String?,
    listenerEnabled: Boolean,
    batteryOptimizationIgnored: Boolean,
    onSignIn: () -> Unit,
    onGrantListener: () -> Unit,
    onExemptBatteryOptimization: () -> Unit,
    onOpenRules: () -> Unit,
) {
    Scaffold(topBar = { CenterAlignedTopAppBar(title = { Text("Notification Relay") }) }) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .padding(16.dp)
                .fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            StatusCard(
                title = "Google account",
                statusText = signedInEmail?.let { "Signed in as $it" } ?: "Not signed in",
                isOk = signedInEmail != null,
                actionLabel = if (signedInEmail == null) "Sign in with Google" else null,
                onAction = onSignIn,
            )
            StatusCard(
                title = "Notification access",
                statusText = if (listenerEnabled) "Granted" else "Not granted",
                isOk = listenerEnabled,
                actionLabel = if (!listenerEnabled) "Grant access" else null,
                onAction = onGrantListener,
            )
            StatusCard(
                title = "Battery optimization",
                statusText = if (batteryOptimizationIgnored) {
                    "Exempt — won't be paused in the background"
                } else {
                    "Not exempt — the OS may delay or drop notifications while backgrounded"
                },
                isOk = batteryOptimizationIgnored,
                actionLabel = if (!batteryOptimizationIgnored) "Exempt this app" else null,
                onAction = onExemptBatteryOptimization,
            )
            Spacer(Modifier.weight(1f))
            FilledTonalButton(onClick = onOpenRules, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Default.List, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("Manage rules")
            }
        }
    }
}

@Composable
private fun StatusCard(
    title: String,
    statusText: String,
    isOk: Boolean,
    actionLabel: String?,
    onAction: () -> Unit,
) {
    ElevatedCard(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    if (isOk) Icons.Default.CheckCircle else Icons.Default.Warning,
                    contentDescription = null,
                    tint = if (isOk) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                )
                Spacer(Modifier.width(8.dp))
                Text(title, style = MaterialTheme.typography.titleMedium)
            }
            Text(
                statusText,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp, start = 32.dp),
            )
            if (actionLabel != null) {
                Spacer(Modifier.height(12.dp))
                Button(onClick = onAction) { Text(actionLabel) }
            }
        }
    }
}

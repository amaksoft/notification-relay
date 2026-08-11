package com.amaksoft.notifrelay.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow

/**
 * Type-to-filter picker constrained to a known option list — the whole
 * point (per explicit user feedback) is that the value that ends up
 * submitted always comes from tapping a real option, never free-typed,
 * so there's no way to submit a package/channel that doesn't actually
 * exist on the device.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun <T> AutocompleteField(
    label: String,
    options: List<T>,
    optionLabel: (T) -> String,
    optionSubtitle: (T) -> String? = { null },
    onOptionSelected: (T) -> Unit,
    modifier: Modifier = Modifier,
    initialQuery: String = "",
    enabled: Boolean = true,
    supportingText: String? = null,
    leadingIcon: (@Composable (T) -> Unit)? = null,
) {
    var expanded by remember { mutableStateOf(false) }
    var query by remember(initialQuery) { mutableStateOf(initialQuery) }
    val filtered = remember(query, options) {
        if (query.isBlank()) options
        else options.filter {
            optionLabel(it).contains(query, ignoreCase = true) ||
                (optionSubtitle(it)?.contains(query, ignoreCase = true) == true)
        }
    }

    ExposedDropdownMenuBox(
        expanded = expanded && filtered.isNotEmpty(),
        onExpandedChange = { if (enabled) expanded = it },
        modifier = modifier,
    ) {
        OutlinedTextField(
            value = query,
            onValueChange = {
                query = it
                expanded = true
            },
            label = { Text(label) },
            supportingText = supportingText?.let { { Text(it) } },
            singleLine = true,
            enabled = enabled,
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(),
        )
        ExposedDropdownMenu(
            expanded = expanded && filtered.isNotEmpty(),
            onDismissRequest = { expanded = false },
        ) {
            filtered.take(50).forEach { option ->
                DropdownMenuItem(
                    leadingIcon = leadingIcon?.let { render -> { render(option) } },
                    text = {
                        Column {
                            Text(optionLabel(option), maxLines = 1, overflow = TextOverflow.Ellipsis)
                            optionSubtitle(option)?.let {
                                Text(
                                    it,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                        }
                    },
                    onClick = {
                        query = optionLabel(option)
                        expanded = false
                        onOptionSelected(option)
                    },
                )
            }
        }
    }
}

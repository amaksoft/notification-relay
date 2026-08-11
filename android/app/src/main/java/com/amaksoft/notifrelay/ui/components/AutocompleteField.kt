package com.amaksoft.notifrelay.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

private const val MAX_VISIBLE_SUGGESTIONS = 20

/** Minimum room a suggestion list needs below the field before we'd
 * rather flip it above instead — roughly two rows' worth. */
private val MIN_SPACE_BELOW = 120.dp

/**
 * Type-to-filter picker constrained to a known option list — the whole
 * point (per explicit user feedback) is that the value that ends up
 * submitted always comes from tapping a real option, never free-typed,
 * so there's no way to submit a package/channel that doesn't actually
 * exist on the device.
 *
 * Deliberately NOT built on ExposedDropdownMenuBox/Popup: inside a
 * ModalBottomSheet with imePadding()+verticalScroll(), a Popup's
 * position is computed from the anchor's on-screen coordinates at
 * composition time and doesn't reliably re-anchor once the IME shifts
 * the layout — in practice the suggestion list rendered detached,
 * floating over unrelated fields above the keyboard instead of right
 * below the text field (confirmed on-device). Rendering suggestions
 * inline instead — as regular content in the normal layout flow, placed
 * before or after the field in the same Column — sidesteps that whole
 * class of bug, and additionally lets us flip the list above the field
 * (like a native dropdown would) by simply changing which side of the
 * field it's declared on, no custom Layout/Popup needed.
 */
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
    val focusManager = LocalFocusManager.current
    val density = LocalDensity.current
    val viewHeightPx = LocalView.current.height
    var query by remember(initialQuery) { mutableStateOf(initialQuery) }
    var focused by remember { mutableStateOf(false) }
    var fieldBounds by remember { mutableStateOf<Rect?>(null) }
    val filtered = remember(query, options) {
        if (query.isBlank()) options
        else options.filter {
            optionLabel(it).contains(query, ignoreCase = true) ||
                (optionSubtitle(it)?.contains(query, ignoreCase = true) == true)
        }
    }

    // Recomputed whenever the IME inset changes (keyboard opening/
    // closing/resizing) or the field moves (scroll), since both affect
    // how much room is actually left below the field.
    val imeBottomPx = WindowInsets.ime.getBottom(density)
    val renderAbove = remember(imeBottomPx, fieldBounds, viewHeightPx) {
        val bounds = fieldBounds ?: return@remember false
        val availableBelow = viewHeightPx - imeBottomPx - bounds.bottom
        val availableAbove = bounds.top
        val minNeededPx = with(density) { MIN_SPACE_BELOW.toPx() }
        availableBelow < minNeededPx && availableAbove > availableBelow
    }

    val showSuggestions = focused && filtered.isNotEmpty()

    fun select(option: T) {
        query = optionLabel(option)
        focusManager.clearFocus()
        onOptionSelected(option)
    }

    Column(modifier = modifier) {
        if (renderAbove && showSuggestions) {
            SuggestionsList(filtered, optionLabel, optionSubtitle, leadingIcon, ::select)
        }
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            label = { Text(label) },
            supportingText = supportingText?.let { { Text(it) } },
            singleLine = true,
            enabled = enabled,
            modifier = Modifier
                .fillMaxWidth()
                .onFocusChanged { focused = it.isFocused }
                .onGloballyPositioned { fieldBounds = it.boundsInWindow() },
        )
        if (!renderAbove && showSuggestions) {
            SuggestionsList(filtered, optionLabel, optionSubtitle, leadingIcon, ::select)
        }
    }
}

@Composable
private fun <T> SuggestionsList(
    options: List<T>,
    optionLabel: (T) -> String,
    optionSubtitle: (T) -> String?,
    leadingIcon: (@Composable (T) -> Unit)?,
    onSelect: (T) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(4.dp)),
    ) {
        options.take(MAX_VISIBLE_SUGGESTIONS).forEach { option ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onSelect(option) }
                    .background(MaterialTheme.colorScheme.surfaceContainer)
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                leadingIcon?.let { render ->
                    render(option)
                    Spacer(Modifier.width(12.dp))
                }
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
            }
        }
    }
}

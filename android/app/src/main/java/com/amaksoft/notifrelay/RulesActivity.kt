package com.amaksoft.notifrelay

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.amaksoft.notifrelay.ui.RulesScreen
import com.amaksoft.notifrelay.ui.theme.NotifRelayTheme

class RulesActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            NotifRelayTheme {
                val viewModel: RulesViewModel = viewModel()
                val rules by viewModel.rules.collectAsStateWithLifecycle()
                val seenChannels by viewModel.seenChannels.collectAsStateWithLifecycle()

                RulesScreen(
                    rules = rules,
                    installedApps = viewModel.installedApps,
                    seenChannels = seenChannels,
                    onPackageSelected = viewModel::loadChannelsFor,
                    onToggle = viewModel::toggleRule,
                    onDelete = viewModel::deleteRule,
                    onAddRule = viewModel::addRule,
                )
            }
        }
    }
}

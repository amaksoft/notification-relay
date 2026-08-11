package com.amaksoft.notifrelay

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.lifecycleScope
import com.amaksoft.notifrelay.ui.MainScreen
import com.amaksoft.notifrelay.ui.theme.NotifRelayTheme
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInClient
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.GoogleAuthProvider
import com.google.firebase.functions.FirebaseFunctions
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

class MainActivity : ComponentActivity() {

    companion object {
        private const val TAG = "MainActivity"
    }

    private lateinit var googleSignInClient: GoogleSignInClient
    private val auth = FirebaseAuth.getInstance()

    private var signedInEmail by mutableStateOf<String?>(null)
    private var listenerEnabled by mutableStateOf(false)
    private var batteryOptimizationIgnored by mutableStateOf(false)
    private var isSigningIn by mutableStateOf(false)

    private val signInLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        try {
            val account = GoogleSignIn.getSignedInAccountFromIntent(result.data).result
            val credential = GoogleAuthProvider.getCredential(account.idToken, null)
            auth.signInWithCredential(credential).addOnCompleteListener {
                isSigningIn = false
                refreshState()
                if (it.isSuccessful) reportDeviceStatus()
            }
        } catch (e: Exception) {
            isSigningIn = false
            Log.w(TAG, "Google sign-in failed or was cancelled", e)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val gso = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
            .requestIdToken(getString(R.string.default_web_client_id))
            .requestEmail()
            .build()
        googleSignInClient = GoogleSignIn.getClient(this, gso)

        setContent {
            NotifRelayTheme {
                MainScreen(
                    signedInEmail = signedInEmail,
                    listenerEnabled = listenerEnabled,
                    batteryOptimizationIgnored = batteryOptimizationIgnored,
                    isSigningIn = isSigningIn,
                    onSignIn = {
                        isSigningIn = true
                        signInLauncher.launch(googleSignInClient.signInIntent)
                    },
                    onSignOut = {
                        auth.signOut()
                        googleSignInClient.signOut().addOnCompleteListener { refreshState() }
                    },
                    onManageListener = { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) },
                    onManageBatteryOptimization = {
                        if (batteryOptimizationIgnored) {
                            // There's no API for an app to drop its own exemption; send the
                            // user to the full app list where they can flip it back off.
                            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                        } else {
                            startActivity(
                                Intent(
                                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                                    Uri.parse("package:$packageName"),
                                )
                            )
                        }
                    },
                    onOpenRules = { startActivity(Intent(this, RulesActivity::class.java)) },
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        refreshState()
        if (auth.currentUser != null) reportDeviceStatus()
    }

    private fun refreshState() {
        signedInEmail = auth.currentUser?.email
        listenerEnabled = NotificationManagerCompat.getEnabledListenerPackages(this).contains(packageName)
        val powerManager = getSystemService(POWER_SERVICE) as PowerManager
        batteryOptimizationIgnored = powerManager.isIgnoringBatteryOptimizations(packageName)
    }

    private fun reportDeviceStatus() {
        lifecycleScope.launch {
            val installedApps = JSONArray().apply {
                InstalledApps.list(this@MainActivity).forEach {
                    put(JSONObject().put("package", it.packageName).put("label", it.label))
                }
            }
            val payload = hashMapOf<String, Any?>(
                "deviceId" to DeviceId.get(this@MainActivity),
                "installedApps" to jsonArrayToList(installedApps),
            )
            try {
                FirebaseFunctions.getInstance().getHttpsCallable("report_device_status").call(payload)
            } catch (e: Exception) {
                // Best-effort; the next onResume (or the next matched
                // notification's own callable calls, which independently
                // establish auth) will retry this naturally. Still logged
                // so a persistent failure is actually diagnosable.
                Log.w(TAG, "report_device_status call failed", e)
            }
        }
    }

    private fun jsonArrayToList(array: JSONArray): List<Map<String, Any?>> =
        (0 until array.length()).map { i ->
            val obj = array.getJSONObject(i)
            obj.keys().asSequence().associateWith { key -> obj.get(key) }
        }
}
